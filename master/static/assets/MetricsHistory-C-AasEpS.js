import { A as __toESM, C as Activity, D as require_jsx_runtime, T as useNodeStore, a as CartesianGrid, f as Server, i as Area, k as require_react, m as RefreshCw, n as YAxis, o as Tooltip, r as XAxis, s as ResponsiveContainer, t as AreaChart, x as CircleAlert, y as Clock } from "./index-Bx2nV5tT.js";
//#region src/plugins/metrics/pages/MetricsHistory.tsx
var import_react = /* @__PURE__ */ __toESM(require_react(), 1);
var import_jsx_runtime = require_jsx_runtime();
var MetricsHistory = ({ api }) => {
	const { nodes } = useNodeStore();
	const [history, setHistory] = (0, import_react.useState)([]);
	const [loading, setLoading] = (0, import_react.useState)(true);
	const [selectedNode, setSelectedNode] = (0, import_react.useState)("all");
	const [period, setPeriod] = (0, import_react.useState)("24h");
	(0, import_react.useEffect)(() => {
		const doFetch = async () => {
			setLoading(true);
			try {
				let url = `/history?period=${period}`;
				if (selectedNode !== "all") url += `&node_id=${selectedNode}`;
				setHistory((await api.fetch(url))?.history || []);
			} catch (err) {
				console.error("Failed to fetch metrics history:", err);
				api.toast(err instanceof Error ? err.message : "Erreur lors du chargement de l'historique", "error");
			} finally {
				setLoading(false);
			}
		};
		doFetch();
	}, [
		selectedNode,
		period,
		api
	]);
	const formatXAxis = (tickItem) => {
		const d = /* @__PURE__ */ new Date(tickItem * 1e3);
		if (period === "1h" || period === "6h") return d.toLocaleTimeString([], {
			hour: "2-digit",
			minute: "2-digit"
		});
		return d.toLocaleDateString([], {
			month: "short",
			day: "numeric",
			hour: "2-digit"
		});
	};
	const formatTooltipDate = (label) => {
		return (/* @__PURE__ */ new Date(Number(label) * 1e3)).toLocaleString();
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "p-6 max-w-7xl mx-auto flex flex-col gap-6 animate-fade-in",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h1", {
					className: "text-2xl font-bold text-text-1 flex items-center gap-2",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Activity, { className: "w-6 h-6 text-accent" }), "Historique des Métriques"]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "text-sm text-text-3 mt-1",
					children: "Supervisez les tendances d'utilisation des ressources système de votre flotte."
				})] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					onClick: fetchHistory,
					disabled: loading,
					className: "flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: `w-3.5 h-3.5 ${loading ? "animate-spin" : ""}` }), "Rafraîchir"]
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "flex flex-col md:flex-row gap-4 p-4 rounded-xl bg-surface-2/40 border border-border-strong/30 backdrop-blur-xs",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex flex-wrap gap-4 items-center flex-1",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center gap-2",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Server, { className: "w-4 h-4 text-text-3" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-xs text-text-3 font-mono uppercase",
								children: "Serveur:"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
								value: selectedNode,
								onChange: (e) => setSelectedNode(e.target.value),
								className: "px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "all",
									children: "Tous les serveurs"
								}), nodes.map((n) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: n.id,
									children: n.name
								}, n.id))]
							})
						]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center gap-2",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Clock, { className: "w-4 h-4 text-text-3" }),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "text-xs text-text-3 font-mono uppercase",
								children: "Période:"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
								value: period,
								onChange: (e) => setPeriod(e.target.value),
								className: "px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "1h",
										children: "Dernière heure"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "6h",
										children: "Dernières 6 heures"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "24h",
										children: "Dernières 24 heures"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
										value: "7d",
										children: "Derniers 7 jours"
									})
								]
							})
						]
					})]
				})
			}),
			loading && history.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-2xl border border-zinc-800/40",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-zinc-500 text-sm font-mono",
					children: "Chargement de l'historique..."
				})]
			}) : history.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleAlert, { className: "w-12 h-12 text-zinc-600 mb-4" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", {
						className: "text-lg font-bold text-zinc-300",
						children: "Aucune métrique enregistrée"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "text-zinc-500 text-sm max-w-md mt-1",
						children: "Aucun point de métrique n'est encore enregistré pour la période et le serveur sélectionnés."
					})
				]
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "grid grid-cols-1 lg:grid-cols-2 gap-6",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h3", {
						className: "text-sm font-bold uppercase font-mono text-text-2 flex items-center gap-2",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Activity, { className: "w-4 h-4 text-orange-500" }), "Utilisation du Processeur (CPU)"]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "h-64",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ResponsiveContainer, {
							width: "100%",
							height: "100%",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AreaChart, {
								data: history,
								margin: {
									top: 10,
									right: 10,
									left: -20,
									bottom: 0
								},
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("defs", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("linearGradient", {
										id: "cpuColor",
										x1: "0",
										y1: "0",
										x2: "0",
										y2: "1",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("stop", {
											offset: "5%",
											stopColor: "#f97316",
											stopOpacity: .2
										}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("stop", {
											offset: "95%",
											stopColor: "#f97316",
											stopOpacity: 0
										})]
									}) }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CartesianGrid, {
										strokeDasharray: "3 3",
										stroke: "#27272a/30"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(XAxis, {
										dataKey: "collected_at",
										tickFormatter: formatXAxis,
										stroke: "#71717a",
										fontSize: 10
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(YAxis, {
										domain: [0, 100],
										stroke: "#71717a",
										fontSize: 10
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Tooltip, {
										labelFormatter: formatTooltipDate,
										contentStyle: {
											backgroundColor: "#18181b",
											borderColor: "#27272a",
											color: "#f4f4f5"
										}
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Area, {
										type: "monotone",
										dataKey: "cpu_percent",
										stroke: "#f97316",
										fillOpacity: 1,
										fill: "url(#cpuColor)",
										name: "CPU (%)"
									})
								]
							})
						})
					})]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("h3", {
						className: "text-sm font-bold uppercase font-mono text-text-2 flex items-center gap-2",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Activity, { className: "w-4 h-4 text-emerald-500" }), "Utilisation de la Mémoire RAM"]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "h-64",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ResponsiveContainer, {
							width: "100%",
							height: "100%",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(AreaChart, {
								data: history,
								margin: {
									top: 10,
									right: 10,
									left: -20,
									bottom: 0
								},
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("defs", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("linearGradient", {
										id: "memColor",
										x1: "0",
										y1: "0",
										x2: "0",
										y2: "1",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("stop", {
											offset: "5%",
											stopColor: "#10b981",
											stopOpacity: .2
										}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("stop", {
											offset: "95%",
											stopColor: "#10b981",
											stopOpacity: 0
										})]
									}) }),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CartesianGrid, {
										strokeDasharray: "3 3",
										stroke: "#27272a/30"
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(XAxis, {
										dataKey: "collected_at",
										tickFormatter: formatXAxis,
										stroke: "#71717a",
										fontSize: 10
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(YAxis, {
										domain: [0, 100],
										stroke: "#71717a",
										fontSize: 10
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Tooltip, {
										labelFormatter: formatTooltipDate,
										contentStyle: {
											backgroundColor: "#18181b",
											borderColor: "#27272a",
											color: "#f4f4f5"
										}
									}),
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Area, {
										type: "monotone",
										dataKey: "mem_percent",
										stroke: "#10b981",
										fillOpacity: 1,
										fill: "url(#memColor)",
										name: "RAM (%)"
									})
								]
							})
						})
					})]
				})]
			})
		]
	});
};
//#endregion
export { MetricsHistory, MetricsHistory as default };
