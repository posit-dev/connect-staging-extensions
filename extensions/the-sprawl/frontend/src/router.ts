import { createRouter, createWebHistory } from "vue-router";
import TracesTableView from "./components/TracesTableView.vue";
import TraceDetailView from "./components/TraceDetailView.vue";
import LogsView from "./components/LogsView.vue";

const router = createRouter({
  history: createWebHistory(new URL(document.baseURI).pathname),
  routes: [
    { path: "/", redirect: "/traces" },
    { path: "/traces", name: "traces", component: TracesTableView },
    { path: "/traces/:traceId", name: "trace-detail", component: TraceDetailView },
    { path: "/logs", name: "logs", component: LogsView },
  ],
});

export default router;
