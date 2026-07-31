import { D as require_jsx_runtime, S as ArrowLeft, k as require_react, u as Terminal, v as Info } from "./index-DXPZvgYx.js";
require_react();
var import_jsx_runtime = require_jsx_runtime();
var DockerContainerDetail = ({ api, routeParams }) => {
	const containerId = routeParams.containerId || "unknown";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "p-6 max-w-4xl mx-auto flex flex-col gap-6 animate-fade-in",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
				onClick: () => api.navigate("/containers"),
				className: "flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-text-3 hover:text-text-1 mb-4 transition-colors cursor-pointer",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ArrowLeft, { className: "w-3.5 h-3.5" }), "Retour aux conteneurs"]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h1", {
				className: "text-2xl font-bold text-text-1 flex items-center gap-2",
				children: ["🐳 Conteneur ", containerId.slice(0, 12)]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "text-sm text-text-3 mt-1",
				children: "Inspection détaillée et logs en streaming."
			})
		] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid grid-cols-1 md:grid-cols-3 gap-6",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "md:col-span-1 p-5 rounded-xl border border-border-strong/30 bg-surface-2/40 backdrop-blur-xs flex flex-col gap-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h3", {
					className: "text-sm font-bold uppercase font-mono text-text-3 flex items-center gap-2",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Info, { className: "w-4 h-4 text-zinc-500" }), "Métadonnées"]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex flex-col gap-2 font-mono text-xs",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-text-3",
						children: "ID:"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-text-1 ml-2 select-all",
						children: containerId
					})] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-text-3",
						children: "Status:"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-green-custom ml-2 font-semibold",
						children: "Running"
					})] })]
				})]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "md:col-span-2 p-5 rounded-xl border border-border-strong/30 bg-zinc-950 flex flex-col gap-3 min-h-[300px]",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h3", {
					className: "text-sm font-bold uppercase font-mono text-zinc-400 flex items-center gap-2 border-b border-zinc-800 pb-2",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Terminal, { className: "w-4 h-4 text-zinc-500 animate-pulse" }), "Logs de sortie"]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex-1 font-mono text-xs text-zinc-400 overflow-y-auto max-h-[400px] flex flex-col gap-1 select-text",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-zinc-600",
							children: "[2026-07-14 10:52:11] Starting server..."
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-green-custom/80",
							children: "[2026-07-14 10:52:12] Database connection established successfully."
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-zinc-500",
							children: "[2026-07-14 10:52:15] Server listening on port 8080."
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-zinc-500",
							children: "[2026-07-14 10:54:02] GET /health - 200 OK"
						})
					]
				})]
			})]
		})]
	});
};
//#endregion
export { DockerContainerDetail, DockerContainerDetail as default };
