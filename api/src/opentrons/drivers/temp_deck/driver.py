from os import environ
import logging
from threading import Event, Thread
from time import sleep
from typing import Optional
from serial.serialutil import SerialException

from opentrons.drivers import serial_communication
from opentrons.drivers.serial_communication import SerialNoResponse

'''
- Driver is responsible for providing an interface for the temp-deck
- Driver is the only system component that knows about the temp-deck's GCODES
  or how the temp-deck communications

- Driver is NOT responsible interpreting the temperatures or states in any way
  or knowing anything about what the device is being used for
'''

log = logging.getLogger(__name__)

ERROR_KEYWORD = 'error'
ALARM_KEYWORD = 'alarm'

DEFAULT_TEMP_DECK_TIMEOUT = 1

DEFAULT_STABILIZE_DELAY = 0.1
DEFAULT_COMMAND_RETRIES = 3

GCODES = {
    'GET_TEMP': 'M105',
    'SET_TEMP': 'M104',
    'DEVICE_INFO': 'M115',
    'DISENGAGE': 'M18',
    'PROGRAMMING_MODE': 'dfu'
}

TEMP_DECK_BAUDRATE = 115200

TEMP_DECK_COMMAND_TERMINATOR = '\r\n\r\n'
TEMP_DECK_ACK = 'ok\r\nok\r\n'

# Number of digits after the decimal point for temperatures being sent
# to/from Temp-Deck
GCODE_ROUNDING_PRECISION = 0


class TempDeckError(Exception):
    pass


class ParseError(Exception):
    pass


def _parse_string_value_from_substring(substring) -> str:
    '''
    Returns the ascii value in the expected string "N:aa11bb22", where "N" is
    the key, and "aa11bb22" is string value to be returned
    '''
    try:
        value = substring.split(':')[1]
        return str(value)
    except (ValueError, IndexError, TypeError, AttributeError):
        log.exception('Unexpected arg to _parse_string_value_from_substring:')
        raise ParseError(
            'Unexpected arg to _parse_string_value_from_substring: {}'.format(
                substring))


def _parse_number_from_substring(substring) -> Optional[float]:
    '''
    Returns the number in the expected string "N:12.3", where "N" is the
    key, and "12.3" is a floating point value

    For the temp-deck's temperature response, one expected input is something
    like "T:none", where "none" should return a None value
    '''
    try:
        value = substring.split(':')[1]
        if value.strip().lower() == 'none':
            return None
        return round(float(value), GCODE_ROUNDING_PRECISION)
    except (ValueError, IndexError, TypeError, AttributeError):
        log.exception('Unexpected argument to _parse_number_from_substring:')
        raise ParseError(
            'Unexpected argument to _parse_number_from_substring: {}'.format(
                substring))


def _parse_key_from_substring(substring) -> str:
    '''
    Returns the axis in the expected string "N:12.3", where "N" is the
    key, and "12.3" is a floating point value
    '''
    try:
        return substring.split(':')[0]
    except (ValueError, IndexError, TypeError, AttributeError):
        log.exception('Unexpected argument to _parse_key_from_substring:')
        raise ParseError(
            'Unexpected argument to _parse_key_from_substring: {}'.format(
                substring))


def _parse_temperature_response(temperature_string) -> dict:
    '''
    Example input: "T:none C:25"
    '''
    err_msg = 'Unexpected argument to _parse_temperature_response: {}'.format(
        temperature_string)
    if not temperature_string or \
            not isinstance(temperature_string, str):
        raise ParseError(err_msg)
    parsed_values = temperature_string.strip().split(' ')
    if len(parsed_values) < 2:
        log.error(err_msg)
        raise ParseError(err_msg)

    data = {
        _parse_key_from_substring(s): _parse_number_from_substring(s)
        for s in parsed_values[:2]
    }
    if 'C' not in data or 'T' not in data:
        raise ParseError(err_msg)
    data = {
        'current': data['C'],
        'target': data['T']
    }
    return data


def _parse_device_information(device_info_string) -> dict:
    '''
        Parse the temp-deck's device information response.

        Example response from temp-deck: "serial:aa11 model:bb22 version:cc33"
    '''
    error_msg = 'Unexpected argument to _parse_device_information: {}'.format(
        device_info_string)
    if not device_info_string or \
            not isinstance(device_info_string, str):
        raise ParseError(error_msg)
    parsed_values = device_info_string.strip().split(' ')
    if len(parsed_values) < 3:
        log.error(error_msg)
        raise ParseError(error_msg)
    res = {
        _parse_key_from_substring(s): _parse_string_value_from_substring(s)
        for s in parsed_values[:3]
    }
    for key in ['model', 'version', 'serial']:
        if key not in res:
            raise ParseError(error_msg)
    return res


class TempDeck:
    def __init__(self, config={}):
        self.run_flag = Event()
        self.run_flag.set()

        self._connection = None
        self._config = config

        self._temperature = {'current': 25, 'target': None}
        self._update_thread = None

    def connect(self, port=None) -> Optional[str]:
        if environ.get('ENABLE_VIRTUAL_SMOOTHIE', '').lower() == 'true':
            return None
        try:
            self.disconnect()
            self._connect_to_port(port)
            self._wait_for_ack()  # verify the device is there
        except (SerialException, SerialNoResponse) as e:
            return str(e)
        return ''

    def disconnect(self):
        if self.is_connected():
            self._connection.close()
        self._connection = None

    def is_connected(self) -> bool:
        if not self._connection:
            return False
        return self._connection.is_open

    @property
    def port(self) -> Optional[str]:
        if not self._connection:
            return None
        return self._connection.port

    # TODO: change to 'deactivate'/'stop'
    def disengage(self) -> str:
        self.run_flag.wait()

        try:
            self._send_command(GCODES['DISENGAGE'])
        except (TempDeckError, SerialException, SerialNoResponse) as e:
            return str(e)
        return ''

    def set_temperature(self, celsius) -> str:
        self.run_flag.wait()
        try:
            celsius = round(float(celsius), GCODE_ROUNDING_PRECISION)
            self._send_command(
                '{0} S{1}'.format(GCODES['SET_TEMP'], celsius))
        except (TempDeckError, SerialException, SerialNoResponse) as e:
            return str(e)
        return ''

    def update_temperature(self, default=None) -> str:
        if self._update_thread and self._update_thread.is_alive():
            updated_temperature = default or self._temperature.copy()
            self._temperature.update(updated_temperature)
        else:
            try:
                self._update_thread = Thread(
                    target=self._recursive_update_temperature,
                    args=[DEFAULT_COMMAND_RETRIES],
                    name='Tempdeck recursive update temperature')
                self._update_thread.start()
            except (TempDeckError, SerialException, SerialNoResponse) as e:
                return str(e)
        return ''

    @property
    def target(self) -> int:
        return self._temperature.get('target')

    @property
    def temperature(self) -> int:
        return self._temperature.get('current')

    @property
    def status(self) -> str:
        current = self._temperature.get('current')
        target = self._temperature.get('target')
        delta = 0.7
        if target:
            diff = target - current
            if abs(diff) < delta:   # To avoid status fluctuation near target
                return 'holding at target'
            elif diff < 0:
                return 'cooling'
            else:
                return 'heating'
        else:
            return 'idle'

    def get_device_info(self) -> dict:
        '''
        Queries Temp-Deck for it's build version, model, and serial number

        returns: dict
            Where keys are the strings 'version', 'model', and 'serial',
            and each value is a string identifier

            {
                'serial': '1aa11bb22',
                'model': '1aa11bb22',
                'version': '1aa11bb22'
            }

        Example input from Temp-Deck's serial response:
            "serial:aa11bb22 model:aa11bb22 version:aa11bb22"
        '''
        try:
            return self._recursive_get_info(DEFAULT_COMMAND_RETRIES)
        except (TempDeckError, SerialException, SerialNoResponse) as e:
            return {'error': str(e)}

    def pause(self):
        self.run_flag.clear()

    def resume(self):
        self.run_flag.set()

    def enter_programming_mode(self) -> str:
        try:
            self._send_command(GCODES['PROGRAMMING_MODE'])
        except (TempDeckError, SerialException, SerialNoResponse) as e:
            return str(e)
        return ''

    def _connect_to_port(self, port=None):
        try:
            temp_deck = environ.get('OT_TEMP_DECK_ID', None)
            self._connection = serial_communication.connect(
                device_name=temp_deck,
                port=port,
                baudrate=TEMP_DECK_BAUDRATE
            )
        except SerialException:
            # if another process is using the port, pyserial raises an
            # exception that describes a "readiness to read" which is confusing
            error_msg = 'Unable to access Serial port to Temp-Deck. This is '
            error_msg += 'because another process is currently using it, or '
            error_msg += 'the Serial port is disabled on this device (OS)'
            raise SerialException(error_msg)

    def _wait_for_ack(self):
        '''
        This methods writes a sequence of newline characters, which will
        guarantee temp-deck responds with 'ok\r\nok\r\n' within 1 seconds
        '''
        self._send_command('\r\n', timeout=DEFAULT_TEMP_DECK_TIMEOUT)

    # Potential place for command optimization (buffering, flushing, etc)
    def _send_command(self, command, timeout=DEFAULT_TEMP_DECK_TIMEOUT):
        """

        """

        command_line = command + ' ' + TEMP_DECK_COMMAND_TERMINATOR
        ret_code = self._recursive_write_and_return(
            command_line, timeout, DEFAULT_COMMAND_RETRIES)

        # Smoothieware returns error state if a switch was hit while moving
        if (ERROR_KEYWORD in ret_code.lower()) or \
                (ALARM_KEYWORD in ret_code.lower()):
            log.error(
                'Received error message from Temp-Deck: {}'.format(ret_code))
            raise TempDeckError(ret_code)

        return ret_code.strip()

    def _recursive_write_and_return(self, cmd, timeout, retries):
        try:
            return serial_communication.write_and_return(
                cmd,
                TEMP_DECK_ACK,
                self._connection,
                timeout)
        except SerialNoResponse as e:
            retries -= 1
            if retries <= 0:
                raise e
            sleep(DEFAULT_STABILIZE_DELAY)
            if self._connection:
                self._connection.close()
                self._connection.open()
            return self._recursive_write_and_return(
                cmd, timeout, retries)

    def _recursive_update_temperature(self, retries) -> Optional[dict]:
        try:
            res = self._send_command(GCODES['GET_TEMP'])
            res = _parse_temperature_response(res)
            self._temperature.update(res)
            return None
        except ParseError as e:
            retries -= 1
            if retries <= 0:
                raise TempDeckError(e)
            sleep(DEFAULT_STABILIZE_DELAY)
            return self._recursive_update_temperature(retries)

    def _recursive_get_info(self, retries) -> dict:
        try:
            device_info = self._send_command(GCODES['DEVICE_INFO'])
            return _parse_device_information(device_info)
        except ParseError as e:
            retries -= 1
            if retries <= 0:
                raise TempDeckError(e)
            sleep(DEFAULT_STABILIZE_DELAY)
            return self._recursive_get_info(retries)
