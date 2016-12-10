import keyMirror from 'keymirror'
import _ from 'lodash'
import Swagger from 'swagger-client'

const activitiesApi = new Swagger({
  url: '/v3/activities/swagger.json',
  usePromise: true,
  authorizations: {
    headerAuth: new Swagger.ApiKeyAuthorization('Authorization-Token', apiKey, 'header')
  }
});

export const ActivitiesActionType = keyMirror({
  ACTIVITIES_RECEIVE_TAGS: null,
  ACTIVITIES_RECEIVE_TAGSETS: null,
  ACTIVITIES_RECEIVE_COMMENTS: null,
  ACTIVITIES_RECEIVE_SOURCES: null,
  ACTIVITIES_RECEIVE_TAGCOUNTS: null,
  ACTIVITIES_RECEIVE_SUGGESTION: null,
  ACTIVITIES_ENTER_SUGGESTION: null,
  ACTIVITIES_TOGGLE_SOURCE: null,
  ACTIVITIES_TOGGLE_TAGSET: null
});

const receiveTags = (comment, tags) => ({type: ActivitiesActionType.ACTIVITIES_RECEIVE_TAGS, comment, tags});

const receiveTagSets = (tagSets) => ({type: ActivitiesActionType.ACTIVITIES_RECEIVE_TAGSETS, tagSets});

const receiveComments = (comments) => ({type: ActivitiesActionType.ACTIVITIES_RECEIVE_COMMENTS, comments});

const receiveSources = (sources) => ({type: ActivitiesActionType.ACTIVITIES_RECEIVE_SOURCES, sources});

const receiveTagCounts = (counts) => ({type: ActivitiesActionType.ACTIVITIES_RECEIVE_TAGCOUNTS, counts});

const receiveToggleSource = (source) => ({type: ActivitiesActionType.ACTIVITIES_TOGGLE_SOURCE, source});

export const toggleTagSet = (id) => ({type: ActivitiesActionType.ACTIVITIES_TOGGLE_TAGSET, id});

export function initActivities() {
  return (dispatch) => {
    return Promise.all([
      dispatch(fetchTagCounts(false)),
      dispatch(fetchTagSets()),
      dispatch(fetchSources())])
  }
}

export function fetchTagSets() {
  return (dispatch) => activitiesApi.then(
    (api) => api.tagsets.get_tagsets()
      .then(({status, obj}) => obj)
      .then(({tagSets}) => dispatch(receiveTagSets(tagSets)))
      .catch((error) => console.log(error)));
}

export function fetchSources() {
  return (dispatch) => activitiesApi.then(
    (api) => api.sources.get_sources()
      .then(({status, obj}) => obj)
      .then(({sources}) => dispatch(receiveSources(sources)))
      .catch((error) => console.log(error)));
}

export function fetchTagCounts(filterSources = true) {
  return (dispatch, getState) => activitiesApi.then(
    (api) => {
      const counts = filterSources ?
        api.tags.get_source_ids_tags({
          source_ids: _.chain(getState().tagger.sources).filter('active').map('id').value(),
          with_count: true
        }) :
        api.tags.get_tags({with_count: true});
      counts.then(({status, obj}) => obj)
        .then(({counts}) => dispatch(receiveTagCounts(counts)))
        .catch((error) => console.log(error))
    });
}

export function fetchRandomComments(count, sources) {
  return (dispatch) => activitiesApi.then(
    (api) => api.activity.get_source_ids({
      source_ids: _.chain(sources).filter('active').map('id').value(),
      count: count,
      random: true
    }).then(({status, obj}) => obj)
      .then(({activities}) => dispatch(receiveComments(activities)))
      .catch((error) => console.log(error)));
}

function manipulateTags(comment, add, remove) {
  return (dispatch) => activitiesApi.then(
    (api) => api.activity.patch_source_id_activity_id_tags({
      source_id: comment.source.id,
      activity_id: comment.id,
      body: {
        add: add,
        remove: remove,
      }
    }).then(({status, obj}) => obj)
      .then(({tags}) => dispatch(receiveTags(comment, tags)))
      .then(() => dispatch(fetchTagCounts()))
      .catch((error) => console.log(error)));
}

export function toggleSource(source) {
  return (dispatch) => Promise.resolve(dispatch(receiveToggleSource(source))).then(dispatch(fetchTagCounts()));
}

export function toggleCommentTag(comment, tag) {
  return manipulateTags(comment, _.difference([tag], comment.tags), _.intersection(comment.tags, [tag]))
}

export function addCommentTag(comment, tag) {
  return manipulateTags(comment, Array.isArray(tag) ? tag : [tag], []);
}

export function resetCommentTags(comment) {
  return manipulateTags(comment, [], comment.tags);
}