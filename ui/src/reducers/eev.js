import _ from 'lodash';

import {EevActionType} from '../actions/EevActions';

const eev = (state = {
  ws: null,
  api: null,
  conversationId: null,
  watermark: null,
  messages: []
}, action) => {
  switch (action.type) {
    case EevActionType.EEV_RECEIVE_CONVERSATION_ID:
      return _.defaults({conversationId: action.conversationId}, state);
    case EevActionType.EEV_RECEIVE_API:
      return _.defaults({api: action.api}, state);
    case EevActionType.EEV_RECEIVE_WS:
      return _.defaults({ws: action.ws}, state);
    case EevActionType.EEV_RECEIVE_MESSAGES:
      return _.defaults({
        messages: _.unionWith(state.messages, action.messages, (a, b) => a.id == b.id),
      }, state);
    case EevActionType.EEV_RECEIVE_CLEAR_MESSAGES:
      return _.defaults({messages: []}, state);
    default:
      return state;
  }
};

export default eev;