import { t as RotateCw } from "./rotate-cw-DUFUBisG.js";
import { A as __toESM, D as require_jsx_runtime, T as useNodeStore, d as Square, f as Server, h as Play, k as require_react, m as RefreshCw, p as Search, x as CircleAlert } from "./index-DXPZvgYx.js";
//#region src/plugins/docker/pages/DockerContainers.tsx
var import_react = /* @__PURE__ */ __toESM(require_react(), 1);
var import_jsx_runtime = require_jsx_runtime();
var DockerContainers = ({ api }) => {
	const { nodes } = useNodeStore();
	const [containers, setContainers] = (0, import_react.useState)([]);
	const [loading, setLoading] = (0, import_react.useState)(true);
	const [searchTerm, setSearchTerm] = (0, import_react.useState)("");
	const [selectedNode, setSelectedNode] = (0, import_react.useState)("all");
	const [stateFilter, setStateFilter] = (0, import_react.useState)("all");
	const [actionInProgress, setActionInProgress] = (0, import_react.useState)({});
	(0, import_react.useEffect)(() => {
		const doFetch = async () => {
			setLoading(true);
			try {
				const url = selectedNode === "all" ? "/containers" : `/containers?node_id=${selectedNode}`;
				setContainers((await api.fetch(url))?.containers || []);
			} catch (err) {
				console.error("Failed to fetch docker containers:", err);
				api.toast(err instanceof Error ? err.message : "Erreur lors du chargement des conteneurs", "error");
			} finally {
				setLoading(false);
			}
		};
		doFetch();
	}, [selectedNode, api]);
	const handleContainerAction = async (nodeId, containerId, action) => {
		const key = `${nodeId}-${containerId}`;
		setActionInProgress((prev) => ({
			...prev,
			[key]: true
		}));
		try {
			await api.fetch(`/containers/${containerId}/${action}`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ node_id: nodeId })
			});
			api.toast(`Action ${action} envoyée avec succès pour le conteneur ${containerId}`, "success");
			setTimeout(fetchContainers, 2e3);
		} catch (err) {
			console.error(`Failed to trigger action ${action} on container ${containerId}:`, err);
			api.toast(err instanceof Error ? err.message : `L'action ${action} a échoué`, "error");
		} finally {
			setActionInProgress((prev) => ({
				...prev,
				[key]: false
			}));
		}
	};
	const getNodeName = (nodeId) => {
		const n = nodes.find((node) => node.id === nodeId);
		return n ? n.name : nodeId.slice(0, 8);
	};
	const filteredContainers = containers.filter((c) => {
		const matchesSearch = c.name.toLowerCase().includes(searchTerm.toLowerCase()) || c.image.toLowerCase().includes(searchTerm.toLowerCase()) || c.id.toLowerCase().includes(searchTerm.toLowerCase());
		let matchesState = true;
		if (stateFilter === "running") matchesState = c.state.toLowerCase() === "running";
		else if (stateFilter === "stopped") matchesState = c.state.toLowerCase() === "exited" || c.state.toLowerCase() === "created";
		else if (stateFilter === "failed") matchesState = c.state.toLowerCase() === "dead" || c.state.toLowerCase() === "exited" && c.name.includes("fail");
		return matchesSearch && matchesState;
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "p-6 max-w-7xl mx-auto flex flex-col gap-6 animate-fade-in",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
					className: "text-2xl font-bold text-text-1 flex items-center gap-2",
					children: "🐳 Conteneurs Docker"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "text-sm text-text-3 mt-1",
					children: "Gérez et supervisez les conteneurs Docker en temps réel sur l'ensemble de votre flotte."
				})] }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
					onClick: fetchContainers,
					disabled: loading,
					className: "flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: `w-3.5 h-3.5 ${loading ? "animate-spin" : ""}` }), "Rafraîchir"]
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col md:flex-row gap-4 p-4 rounded-xl bg-surface-2/40 border border-border-strong/30 backdrop-blur-xs",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex-1 relative",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Search, { className: "absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-3" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
						type: "text",
						placeholder: "Rechercher par nom, image ou ID...",
						value: searchTerm,
						onChange: (e) => setSearchTerm(e.target.value),
						className: "w-full pl-10 pr-4 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all duration-150"
					})]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "flex flex-wrap gap-4",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center gap-2",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-xs text-text-3 font-mono uppercase",
							children: "Serveur:"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
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
						})]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center gap-2",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-xs text-text-3 font-mono uppercase",
							children: "Statut:"
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
							value: stateFilter,
							onChange: (e) => setStateFilter(e.target.value),
							className: "px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "all",
									children: "Tous les statuts"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "running",
									children: "En cours d'exécution"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "stopped",
									children: "Arrêtés"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "failed",
									children: "Échoués"
								})
							]
						})]
					})]
				})]
			}),
			loading && containers.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-2xl border border-zinc-800/40",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-zinc-500 text-sm font-mono",
					children: "Chargement des conteneurs..."
				})]
			}) : filteredContainers.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-col items-center justify-center py-16 bg-zinc-900/15 rounded-2xl border border-zinc-800/40 text-center px-6",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleAlert, { className: "w-12 h-12 text-zinc-600 mb-4" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", {
						className: "text-lg font-bold text-zinc-300",
						children: "Aucun conteneur trouvé"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "text-zinc-500 text-sm max-w-md mt-1",
						children: "Aucun conteneur Docker ne correspond aux critères de recherche actuels."
					})
				]
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "overflow-x-auto rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("table", {
					className: "w-full text-left border-collapse",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
						className: "border-b border-border-strong/40 bg-surface-2/30 font-mono text-[10px] text-text-3 uppercase tracking-wider select-none",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-6 py-4 font-bold",
								children: "Conteneur"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-6 py-4 font-bold",
								children: "Image"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-6 py-4 font-bold",
								children: "Serveur"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-6 py-4 font-bold",
								children: "Ports"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-6 py-4 font-bold",
								children: "Statut"
							}),
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("th", {
								className: "px-6 py-4 font-bold text-right",
								children: "Actions"
							})
						]
					}) }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("tbody", { children: filteredContainers.map((c) => {
						const key = `${c.node_id}-${c.id}`;
						const inProgress = actionInProgress[key];
						const isRunning = c.state.toLowerCase() === "running";
						return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("tr", {
							className: "border-b border-border-strong/15 hover:bg-surface-2/20 transition-colors duration-150 text-sm",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-6 py-4 font-semibold text-text-1",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "flex flex-col",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: c.name }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
											className: "text-[10px] text-text-3 font-mono mt-0.5",
											children: c.id.slice(0, 12)
										})]
									})
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-6 py-4 text-text-2 font-mono text-xs max-w-[200px] truncate",
									title: c.image,
									children: c.image
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-6 py-4 text-text-2 font-mono text-xs",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
										className: "flex items-center gap-1.5 text-zinc-400",
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Server, { className: "w-3.5 h-3.5 text-zinc-500" }), getNodeName(c.node_id)]
									})
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-6 py-4",
									children: c.ports && c.ports.length > 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "flex flex-wrap gap-1",
										children: [c.ports.slice(0, 3).map((p, idx) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
											className: "text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700/40",
											children: p
										}, idx)), c.ports.length > 3 && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
											className: "text-[9px] font-mono text-zinc-500 px-1",
											children: ["+", c.ports.length - 3]
										})]
									}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
										className: "text-xs text-text-3 font-mono",
										children: "—"
									})
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-6 py-4",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
										className: `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold leading-none ${isRunning ? "bg-green-custom/10 text-green-custom border border-green-custom/20" : "bg-zinc-800 text-zinc-400 border border-zinc-700/50"}`,
										children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: `w-1.5 h-1.5 rounded-full ${isRunning ? "bg-green-custom animate-pulse" : "bg-zinc-500"}` }), c.state]
									})
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("td", {
									className: "px-6 py-4 text-right",
									children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
										className: "flex justify-end gap-2",
										children: [isRunning ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
											onClick: () => handleContainerAction(c.node_id, c.id, "stop"),
											disabled: inProgress,
											className: "p-1.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors border border-transparent hover:border-zinc-700/50 cursor-pointer",
											title: "Arrêter le conteneur",
											children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Square, { className: "w-4 h-4" })
										}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
											onClick: () => handleContainerAction(c.node_id, c.id, "start"),
											disabled: inProgress,
											className: "p-1.5 rounded hover:bg-green-custom/10 text-green-custom hover:text-green-custom transition-colors border border-transparent hover:border-green-custom/20 cursor-pointer",
											title: "Démarrer le conteneur",
											children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Play, { className: "w-4 h-4" })
										}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
											onClick: () => handleContainerAction(c.node_id, c.id, "restart"),
											disabled: inProgress,
											className: "p-1.5 rounded hover:bg-orange-500/10 text-orange-500 hover:text-orange-400 transition-colors border border-transparent hover:border-orange-500/20 cursor-pointer",
											title: "Redémarrer le conteneur",
											children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RotateCw, { className: `w-4 h-4 ${inProgress ? "animate-spin" : ""}` })
										})]
									})
								})
							]
						}, key);
					}) })]
				})
			})
		]
	});
};
//#endregion
export { DockerContainers, DockerContainers as default };
