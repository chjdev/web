import injectTapEventPlugin from "react-tap-event-plugin";

injectTapEventPlugin(); // will go away
import React from "react";
import {render} from "react-dom";
import {Provider} from "react-redux";
import Router from "./components/Router.jsx";
import store from "./store";
import "./app.css";

import {fetchUser} from "./actions/app/user";

render(
  <Provider store={store}>
    <Router/>
  </Provider>,
  document.getElementById('app')
);

store.dispatch(fetchUser());