import React from "react";
import {Router, Route, IndexRoute, browserHistory, DefaultRoute} from "react-router";
import MuiThemeProvider from "material-ui/styles/MuiThemeProvider";
import Footer from "./Footer.jsx";
import Sidebar from "./sidebar/Sidebar.jsx";
import Alerts from "./Alerts.jsx";

const App = ({children}) => (
  <MuiThemeProvider>
    <div style={{display: 'flex', flexDirection: 'column', height: '100%'}}>
      <Sidebar/>
      {children}
      <Footer/>
      <Alerts/>
    </div>
  </MuiThemeProvider>
);

export default App;