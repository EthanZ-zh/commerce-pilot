import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, theme } from "antd";
import "@xyflow/react/dist/style.css";

import App from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, refetchOnWindowFocus: false },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: "#6f7bff",
          colorSuccess: "#57d9a3",
          colorBgBase: "#080d18",
          colorTextBase: "#eef2ff",
          borderRadius: 12,
          fontFamily: "Inter, 'Segoe UI', 'Microsoft YaHei', sans-serif",
        },
        components: {
          Card: { colorBgContainer: "#111827" },
          Table: { colorBgContainer: "transparent", headerBg: "#161f33" },
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ConfigProvider>
  </React.StrictMode>,
);
