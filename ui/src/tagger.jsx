import React from 'react';
import {render} from 'react-dom';
import {createStore, combineReducers, applyMiddleware} from 'redux'
import {Provider} from 'react-redux'
import createLogger from 'redux-logger'
import thunkMiddleware from 'redux-thunk'

import {initEev} from './actions/EevActions'
import {initTagger} from './actions/TaggerActions'
import alerts from './reducers/alerts'
import eev from './reducers/eev'
import tagger from './reducers/tagger'
import app from './reducers/app'

import App from './components/App.jsx'
import AlertsApp from './components/Alerts.jsx'

function initGlobal() {
  return (dispatch) => Promise.all([initEev(), initTagger()]);
}

const store = createStore(
  combineReducers({
    alerts,
    eev,
    tagger,
    app,
  }),
  applyMiddleware(
    thunkMiddleware,
    createLogger()
  )
);

render(
  <Provider store={store}>
    <App />
  </Provider>,
  document.getElementById('app')
);
render(
  <Provider store={store}>
    <AlertsApp />
  </Provider>,
  document.getElementById('alerts')
);

store.dispatch(initEev());
