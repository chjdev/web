import {combineReducers} from 'redux'
import _ from 'lodash';

import {TaggerActionType} from '../actions/TaggerActions'

const comments = (state = {}, action) => {
  switch (action.type) {
    case TaggerActionType.TAGGER_RECEIVE_COMMENTS:
      // todo: maybe hand off in a _.mapValue to comment() to perform some checks
      return _.chain(action.comments)
        .mapValues(comment => _.defaults({
            suggestion: _.chain(comment.suggestion)
              .mapValues(s => s > 0.99 ? 0 : s > 0.95 ? 1 : s > 0.8 ? 2 : 3)  // 0 excellent, 1 good, 2 fair, 3 ignore
              .value()
          }, comment))
        .mapKeys('id')
        .value();
    case TaggerActionType.TAGGER_RECEIVE_TAGS:
      return _.defaults({
        [action.id]: _.defaults({tags: _.uniq(action.tags)}, state[action.id])
      }, state);
    default:
      return state;
  }
}

const sources = (state = JSON.parse(sessionStorage.getItem('tagger_sources')) || {}, action) => {
  let newState = null;
  switch (action.type) {
    case TaggerActionType.TAGGER_RECEIVE_SOURCES:
      newState = _.chain(action.sources).uniq().map(source => [source, {id: source, active: true}]).fromPairs().value();
      break;
    case TaggerActionType.TAGGER_TOGGLE_SOURCE:
      newState = _.defaults({
        [action.id]: _.defaults({active: !state[action.id].active}, state[action.id])
      }, state);
      if (_.every(newState, ['active', false])) {
        newState = _.mapValues(newState, source => _.defaults({active: true}, source));
      }
      break;
    default:
      newState = state;
  }
  sessionStorage.setItem('tagger_sources', JSON.stringify(newState));
  return newState;
}

const tagSets = (state = JSON.parse(sessionStorage.getItem('tagger_tagSets')) || {}, action) => {
  let newState = null
  switch (action.type) {
    case TaggerActionType.TAGGER_TOGGLE_TAGSET:
      newState = _.defaults({
        [action.id]: _.defaults({active: !state[action.id].active}, state[action.id])
      }, state)
      break;
    case TaggerActionType.TAGGER_RECEIVE_TAGSETS:
      newState = _.keyBy(action.tagSets, 'id');
      break;
    default:
      newState = state;
  }
  sessionStorage.setItem('tagger_tagSets', JSON.stringify(newState));
  return newState
}

const stats = (state = {__all: {tags:{}}}, action) => {
  switch (action.type) {
    case TaggerActionType.TAGGER_RECEIVE_STATS:
      return _.defaults({[action.source]: action.stats}, state);
    case TaggerActionType.TAGGER_DISMISS_STATS:
      return _.omit(state, action.source)
    default:
      return state;
  }
}

const evaluator = (state = {loading: false, suggestion: {}}, action) => {
  switch (action.type) {
    case TaggerActionType.TAGGER_RECEIVE_SUGGESTION:
      return _.defaults({loading: false, suggestion: action.suggestion}, state);
    case TaggerActionType.TAGGER_ENTER_SUGGESTION:
      return _.defaults({loading: true}, state);
    default:
      return state;
  }
}

const tagger = combineReducers({
  comments,
  sources,
  tagSets,
  evaluator,
  stats
});

export default tagger