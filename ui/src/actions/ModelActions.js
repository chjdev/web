import keyMirror from "keymirror";
import Swagger from "swagger-client";
import map from "lodash/fp/map";
import {warning} from "./AlertActions";
import resolveToSelf from "./resolveToSelf";

const modelApi = new Swagger({
  url: resolveToSelf('/v3/model/swagger.json'),
  authorizations: {
    api_key: apiKey
  }
});

export const ModelActionType = keyMirror({
  MODEL_RECEIVE_SUGGESTION: null,
  MODEL_RECEIVE_ISFETCHING: null,
});


const receiveSuggestion = (suggestion) => ({type: ModelActionType.MODEL_RECEIVE_SUGGESTION, suggestion});
const receiveIsFetching = (isFetching) => ({type: ModelActionType.MODEL_RECEIVE_ISFETCHING, isFetching});

export const setIsFetching = (isFetching) =>
  (dispatch) => Promise.resolve(dispatch(receiveIsFetching(isFetching)));

export const clearSuggestion = () =>
  (dispatch) => Promise.resolve(dispatch(receiveSuggestion({})));

export const fetchSuggestionForText = ({text, sources, tagSets}) =>
  (dispatch) => modelApi.then(
    (client) => client.apis.prediction.post_prediction({
      body: {
        text,
        source_ids: map('id')(sources),
        tagset_ids: map('id')(tagSets)
      }
    }).then(({status, obj}) => dispatch(receiveSuggestion(obj)))
      .then(() => dispatch(setIsFetching(false)))
      .catch(({response: {obj: {detail, status, title}}}) => {
        console.log(status, title, detail);
        dispatch(warning(detail));
        dispatch(setIsFetching(false));
      }));
