// @flow
import * as React from 'react'
import cx from 'classnames'
import omit from 'lodash/omit'
import reduce from 'lodash/reduce'
import {connect} from 'react-redux'

import {Modal, OutlineButton, LabeledValue} from '@opentrons/components'
import {getPipetteNameSpecs, sortWells} from '@opentrons/shared-data'
import type {BaseState, ThunkDispatch} from '../../../types'
import {selectors as pipetteSelectors} from '../../../pipettes'

import * as wellContentsSelectors from '../../../top-selectors/well-contents'
import {selectors} from '../../../labware-ingred/reducers'
import type {Wells, ContentsByWell} from '../../../labware-ingred/types'
import {selectors as steplistSelectors} from '../../../steplist'
import type {WellIngredientNames} from '../../../steplist/types'
import {changeFormInput} from '../../../steplist/actions'
import type {StepFieldName} from '../../../form-types'
import type {PipetteData} from '../../../step-generation/types'

import {SelectableLabware} from '../../labware'
import SingleLabwareWrapper from '../../SingleLabware'
import WellSelectionInstructions from '../../WellSelectionInstructions'

import styles from './WellSelectionModal.css'
import modalStyles from '../../modals/modal.css'

type OP = {
  pipetteId: ?string,
  labwareId: ?string,
  isOpen: boolean,
  onCloseClick: (e: ?SyntheticEvent<*>) => mixed,
  name: StepFieldName,
}
type SP = {
  pipette: ?PipetteData,
  initialSelectedWells: Array<string>,
  wellContents: ContentsByWell,
  containerType: string,
  ingredNames: WellIngredientNames,
}
type DP = {saveWellSelection: (Wells) => mixed}

type Props = OP & SP & DP
type State = {selectedWells: Wells, highlightedWells: Wells}

class WellSelectionModal extends React.Component<Props, State> {
  state = {selectedWells: {}, highlightedWells: {}}
  constructor (props) {
    super(props)
    const initialSelectedWells = reduce(this.props.initialSelectedWells, (acc, well) => (
      {...acc, [well]: well}
    ), {})
    this.state = {selectedWells: initialSelectedWells, highlightedWells: {}}
  }

  updateHighlightedWells = (wells: Wells) => {
    this.setState({highlightedWells: wells})
  }

  selectWells = (wells: Wells) => {
    this.setState({selectedWells: {...this.state.selectedWells, ...wells}, highlightedWells: {}})
  }

  deselectWells = (wells: Wells) => {
    this.setState({selectedWells: omit(this.state.selectedWells, Object.keys(wells)), highlightedWells: {}})
  }

  handleSave = () => {
    this.props.saveWellSelection(this.state.selectedWells)
    this.props.onCloseClick()
  }

  render () {
    if (!this.props.isOpen) return null
    const {pipette} = this.props
    const pipetteConfig = pipette && getPipetteNameSpecs(pipette.model)

    return (
      <Modal
        className={modalStyles.modal}
        contentsClassName={cx(modalStyles.modal_contents, modalStyles.transparent_content)}
        onCloseClick={this.props.onCloseClick}>
        <div className={styles.top_row}>
          <LabeledValue
            label='Pipette'
            value={pipetteConfig ? pipetteConfig.displayName : ''}
            className={styles.inverted_text}
          />
          <OutlineButton onClick={this.handleSave} inverted>
            SAVE SELECTION
          </OutlineButton>
        </div>

        <SingleLabwareWrapper showLabels>
          <SelectableLabware
            highlightedWells={this.state.highlightedWells}
            selectedWells={this.state.selectedWells}
            selectWells={this.selectWells}
            deselectWells={this.deselectWells}
            updateHighlightedWells={this.updateHighlightedWells}
            wellContents={this.props.wellContents}
            containerType={this.props.containerType}
            pipetteChannels={pipette && pipette.channels}
            ingredNames={this.props.ingredNames} />
        </SingleLabwareWrapper>

        <WellSelectionInstructions />
      </Modal>
    )
  }
}

function mapStateToProps (state: BaseState, ownProps: OP): SP {
  const {pipetteId, labwareId} = ownProps

  const allLabware = selectors.getLabware(state)
  const labware = labwareId && allLabware && allLabware[labwareId]
  const allWellContentsForSteps = wellContentsSelectors.allWellContentsForSteps(state)

  const stepId = steplistSelectors.getSelectedStepId(state)
  // TODO: Ian 2018-07-31 replace with util function, "findIndexOrNull"?
  const orderedSteps = steplistSelectors.orderedSteps(state)
  const timelineIdx = orderedSteps.findIndex(id => id === stepId)
  const allWellContentsForStep = allWellContentsForSteps[timelineIdx]
  const formData = steplistSelectors.getUnsavedForm(state)
  const ingredNames = selectors.getLiquidNamesById(state)

  return {
    initialSelectedWells: formData ? formData[ownProps.name] : [],
    pipette: pipetteId ? pipetteSelectors.equippedPipettes(state)[pipetteId] : null,
    wellContents: labware && allWellContentsForStep ? allWellContentsForStep[labware.id] : {},
    containerType: labware ? labware.type : 'missing labware',
    ingredNames,
  }
}

function mapDispatchToProps (dispatch: ThunkDispatch<*>, ownProps: OP): DP {
  return {
    saveWellSelection: (wells) => dispatch(changeFormInput({
      update: {[ownProps.name]: Object.keys(wells).sort(sortWells)},
    })),
  }
}

export default connect(mapStateToProps, mapDispatchToProps)(WellSelectionModal)
