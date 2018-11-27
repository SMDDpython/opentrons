// @flow
import {createSelector} from 'reselect'

import {selectors as pipetteSelectors} from '../pipettes'
import {selectors as labwareIngredSelectors} from '../labware-ingred/reducers'
import {selectors as steplistSelectors} from '../steplist'
import {selectors as fileDataSelectors} from '../file-data'

import {
  generateSubsteps,
} from '../steplist/generateSubsteps' // TODO Ian 2018-04-11 move generateSubsteps closer to this substeps.js file?

import type {Selector} from '../types'
import type {StepIdType} from '../form-types'
import type {SubstepItemData} from '../steplist/types'

type AllSubsteps = {[StepIdType]: ?SubstepItemData}
export const allSubsteps: Selector<AllSubsteps> = createSelector(
  steplistSelectors.getArgsAndErrorsByStepId,
  pipetteSelectors.equippedPipettes,
  labwareIngredSelectors.getLabwareTypes,
  steplistSelectors.getOrderedSteps,
  fileDataSelectors.robotStateTimeline,
  fileDataSelectors.getInitialRobotState,
  (
    allStepArgsAndErrors,
    allPipetteData,
    allLabwareTypes,
    orderedSteps,
    robotStateTimeline,
    _initialRobotState,
  ) => {
    return orderedSteps.reduce((acc: AllSubsteps, stepId, timelineIndex) => {
      const timeline = [{robotState: _initialRobotState}, ...robotStateTimeline.timeline]
      const robotState = timeline[timelineIndex] && timeline[timelineIndex].robotState

      const substeps = generateSubsteps(
        allStepArgsAndErrors[stepId],
        allPipetteData,
        (labwareId: string) => allLabwareTypes[labwareId],
        robotState,
        stepId
      )

      return {
        ...acc,
        [stepId]: substeps,
      }
    }, {})
  }
)
