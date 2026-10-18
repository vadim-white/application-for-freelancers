import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import { createPinia } from "pinia";

import naive from "naive-ui";
import "./styles/global.css";

const app = createApp(App);

// Pinia раньше роутера: redirect-функция роута «/» читает стор при установке роутера
app.use(createPinia());
app.use(router);
app.use(naive);

app.mount("#app");
