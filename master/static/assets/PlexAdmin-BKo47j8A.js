import { A as __toESM, D as require_jsx_runtime, E as api, O as useAuthStore, T as useNodeStore, _ as Package, b as CircleCheck, c as User, g as Pause, h as Play, k as require_react, l as TriangleAlert, m as RefreshCw, w as createLucideIcon } from "./index-BLT-G1X2.js";
/**
* @license lucide-react v1.16.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Film = createLucideIcon("film", [
	["rect", {
		width: "18",
		height: "18",
		x: "3",
		y: "3",
		rx: "2",
		key: "afitv7"
	}],
	["path", {
		d: "M7 3v18",
		key: "bbkbws"
	}],
	["path", {
		d: "M3 7.5h4",
		key: "zfgn84"
	}],
	["path", {
		d: "M3 12h18",
		key: "1i2n21"
	}],
	["path", {
		d: "M3 16.5h4",
		key: "1230mu"
	}],
	["path", {
		d: "M17 3v18",
		key: "in4fa5"
	}],
	["path", {
		d: "M17 7.5h4",
		key: "myr1c1"
	}],
	["path", {
		d: "M17 16.5h4",
		key: "go4c1d"
	}]
]);
/**
* @license lucide-react v1.16.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Tv = createLucideIcon("tv", [["path", {
	d: "m17 2-5 5-5-5",
	key: "16satq"
}], ["rect", {
	width: "20",
	height: "15",
	x: "2",
	y: "7",
	rx: "2",
	key: "1e6viu"
}]]);
//#endregion
//#region src/plugins/plex/components/PlexSessionsTab.tsx
var import_react = /* @__PURE__ */ __toESM(require_react(), 1);
var import_jsx_runtime = require_jsx_runtime();
var PlexSessionsTab = ({ sessions }) => {
	if (sessions.length === 0) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "text-center py-10 text-text-3 text-xs uppercase tracking-wider font-mono",
		children: "Aucune session de lecture en cours"
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "flex flex-col gap-2",
		children: sessions.map((session, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-center justify-between p-3.5 bg-surface-2/40 border border-border-strong/15 rounded-xl hover:bg-surface-2/70 transition-colors",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "min-w-0 flex items-center gap-3",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "w-8 h-8 rounded-lg bg-orange-500/10 flex items-center justify-center text-orange-500 shrink-0 border border-orange-500/20",
					children: session.state === "playing" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Play, { className: "w-4 h-4 fill-orange-500" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Pause, { className: "w-4 h-4" })
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "min-w-0",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "text-sm font-bold text-text-1 truncate",
						children: [session.grandparent_title ? `${session.grandparent_title} - ` : "", session.title]
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex items-center gap-3 mt-1 text-xs text-text-3",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "flex items-center gap-1",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(User, { className: "w-3.5 h-3.5 text-zinc-500" }),
								" ",
								session.user
							]
						}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "flex items-center gap-1 truncate",
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Tv, { className: "w-3.5 h-3.5 text-zinc-500" }),
								" ",
								session.device || "Inconnu"
							]
						})]
					})]
				})]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "shrink-0 flex items-center gap-1.5 ml-4",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: `text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border ${session.transcode ? "bg-orange-500/10 text-orange-500 border-orange-500/20" : "bg-green-custom/10 text-green-custom border-green-custom/20"}`,
					children: session.transcode ? "Transcode" : "Direct Play"
				})
			})]
		}, i))
	});
};
//#endregion
//#region src/plugins/plex/components/PlexLibrariesTab.tsx
var PlexLibrariesTab = ({ libraries }) => {
	if (libraries.length === 0) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "grid grid-cols-1 md:grid-cols-2 gap-3",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "col-span-2 text-center py-10 text-text-3 text-xs uppercase tracking-wider font-mono",
			children: "Aucune bibliothèque détectée"
		})
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "grid grid-cols-1 md:grid-cols-2 gap-3",
		children: libraries.map((lib, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "p-3.5 bg-surface-2/40 border border-border-strong/15 rounded-xl flex items-center gap-3",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Film, { className: "w-5 h-5 text-orange-500 shrink-0" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "min-w-0",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "text-sm font-bold text-text-1 truncate",
					children: lib.title
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "text-[10px] text-text-3 uppercase font-semibold mt-0.5",
					children: lib.type
				})]
			})]
		}, i))
	});
};
//#endregion
//#region src/plugins/plex/components/PlexUsersTab.tsx
var PlexUsersTab = ({ users }) => {
	if (users.length === 0) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "text-center py-10 text-text-3 text-xs uppercase tracking-wider font-mono",
		children: "Aucun utilisateur Plex trouvé"
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "flex flex-col gap-2",
		children: users.map((u, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex items-center gap-3 p-3.5 bg-surface-2/40 border border-border-strong/15 rounded-xl",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "w-8 h-8 rounded-full bg-orange-500/10 border border-orange-500/20 flex items-center justify-center text-xs font-bold text-orange-500",
				children: u.name ? u.name.substring(0, 2).toUpperCase() : "US"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "text-sm font-bold text-text-1",
				children: u.name || "Utilisateur Plex"
			}), u.default_subtitle_language && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "text-[10px] text-text-3 mt-0.5",
				children: ["Langue des sous-titres : ", u.default_subtitle_language]
			})] })]
		}, i))
	});
};
//#endregion
//#region src/plugins/plex/pages/PlexAdmin.tsx
var PlexAdmin = ({ api: api$1 }) => {
	const { nodes } = useNodeStore();
	const { user } = useAuthStore();
	const isAdmin = user?.role === "admin";
	const [selectedNodeId, setSelectedNodeId] = (0, import_react.useState)("");
	const [plexConnecting, setPlexConnecting] = (0, import_react.useState)(false);
	const [plexPinCode, setPlexPinCode] = (0, import_react.useState)("");
	const [plexLoadingData, setPlexLoadingData] = (0, import_react.useState)(false);
	const [plexDetection, setPlexDetection] = (0, import_react.useState)(null);
	const [plexActiveTab, setPlexActiveTab] = (0, import_react.useState)("sessions");
	const [plexSessions, setPlexSessions] = (0, import_react.useState)([]);
	const [plexLibraries, setPlexLibraries] = (0, import_react.useState)([]);
	const [plexUsers, setPlexUsers] = (0, import_react.useState)([]);
	const plexPollIntervalRef = (0, import_react.useRef)(null);
	const plexPollTimeoutRef = (0, import_react.useRef)(null);
	const clearPlexTimers = () => {
		if (plexPollIntervalRef.current) {
			window.clearInterval(plexPollIntervalRef.current);
			plexPollIntervalRef.current = null;
		}
		if (plexPollTimeoutRef.current) {
			window.clearTimeout(plexPollTimeoutRef.current);
			plexPollTimeoutRef.current = null;
		}
	};
	(0, import_react.useEffect)(() => {
		return () => clearPlexTimers();
	}, []);
	(0, import_react.useEffect)(() => {
		if (nodes.length > 0 && !selectedNodeId) setSelectedNodeId(nodes[0].id);
	}, [nodes, selectedNodeId]);
	const fetchPlexData = (0, import_react.useCallback)(async (nodeId) => {
		if (!nodeId) return;
		setPlexLoadingData(true);
		setPlexDetection(null);
		try {
			const detect = await api$1.fetch(`/${nodeId}/detect`);
			if (detect) {
				setPlexDetection(detect);
				if (detect.detected && detect.configured) {
					const [sessionsData, libraryData, usersData] = await Promise.all([
						api$1.fetch(`/${nodeId}/sessions`).catch(() => ({ sessions: [] })),
						api$1.fetch(`/${nodeId}/library`).catch(() => ({ libraries: [] })),
						api$1.fetch(`/${nodeId}/users`).catch(() => ({ users: [] }))
					]);
					setPlexSessions(sessionsData?.sessions || []);
					setPlexLibraries(libraryData?.libraries || []);
					setPlexUsers(usersData?.users || []);
				}
			}
		} catch (err) {
			console.error("Failed to fetch Plex data:", err);
			api$1.toast("Impossible de récupérer les données du serveur Plex.", "error");
		} finally {
			setPlexLoadingData(false);
		}
	}, [api$1]);
	(0, import_react.useEffect)(() => {
		if (selectedNodeId) fetchPlexData(selectedNodeId);
	}, [selectedNodeId, fetchPlexData]);
	const handleConnectPlex = async () => {
		setPlexConnecting(true);
		clearPlexTimers();
		let clientId = localStorage.getItem("plex_client_id");
		if (!clientId) {
			clientId = "vigile-client-" + Math.random().toString(36).substring(2, 15);
			localStorage.setItem("plex_client_id", clientId);
		}
		try {
			const res = await fetch("https://plex.tv/api/v2/pins?strong=true", {
				method: "POST",
				headers: {
					"Accept": "application/json",
					"X-Plex-Product": "Vigile",
					"X-Plex-Client-Identifier": clientId
				}
			});
			if (!res.ok) throw new Error("Failed to fetch PIN");
			const data = await res.json();
			setPlexPinCode(data.code);
			const authUrl = `https://app.plex.tv/auth#?clientID=${clientId}&code=${data.code}&context%5Bdevice%5D%5Bproduct%5D=Vigile`;
			window.open(authUrl, "Plex Auth", "width=600,height=700");
			plexPollIntervalRef.current = window.setInterval(async () => {
				try {
					const pollData = await (await fetch(`https://plex.tv/api/v2/pins/${data.id}`, { headers: {
						"Accept": "application/json",
						"X-Plex-Client-Identifier": clientId
					} })).json();
					if (pollData.authToken) {
						clearPlexTimers();
						await api("/api/admin/plugins/plex/config", {
							method: "POST",
							body: JSON.stringify({ plex_token: pollData.authToken })
						});
						api$1.toast("Connexion réussie avec Plex !", "success");
						setPlexConnecting(false);
						setPlexPinCode("");
						if (selectedNodeId) fetchPlexData(selectedNodeId);
					}
				} catch (err) {
					console.error("Plex polling error:", err);
				}
			}, 2e3);
			plexPollTimeoutRef.current = window.setTimeout(() => {
				clearPlexTimers();
				setPlexConnecting(false);
				setPlexPinCode("");
				api$1.toast("La connexion avec Plex a expiré.", "error");
			}, 12e4);
		} catch (err) {
			console.error(err);
			api$1.toast("Impossible de démarrer la connexion avec Plex.", "error");
			setPlexConnecting(false);
		}
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "p-6 max-w-5xl mx-auto flex flex-col gap-6 animate-fade-in",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
				className: "text-2xl font-bold text-text-1 flex items-center gap-2",
				children: "🎬 Plex Media Server"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "text-sm text-text-3 mt-1",
				children: "Supervisez l'activité et configurez le serveur Plex de votre flotte."
			})] }), selectedNodeId && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
				onClick: () => fetchPlexData(selectedNodeId),
				disabled: plexLoadingData,
				className: "flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border-strong/50 bg-surface-2 hover:bg-surface-hover/80 text-text-1 font-mono text-xs font-semibold uppercase tracking-wider cursor-pointer transition-colors duration-150 disabled:opacity-50",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RefreshCw, { className: `w-3.5 h-3.5 ${plexLoadingData ? "animate-spin" : ""}` }), "Rafraîchir"]
			})]
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "grid grid-cols-1 lg:grid-cols-3 gap-6",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "lg:col-span-1 flex flex-col gap-6",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "p-5 rounded-xl border border-border-strong/30 bg-surface-2/40 backdrop-blur-xs flex flex-col gap-3",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", {
						className: "text-xs font-mono font-bold uppercase tracking-wider text-text-3",
						children: "Serveur Cible (Node)"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
						value: selectedNodeId,
						onChange: (e) => setSelectedNodeId(e.target.value),
						className: "w-full px-3 py-2 text-sm rounded-lg border border-border bg-surface text-text-1 focus:outline-none focus:border-accent transition-all duration-150",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: "",
							children: "-- Choisir un nœud --"
						}), nodes.map((node) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: node.id,
							children: node.name
						}, node.id))]
					})]
				}), isAdmin && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "p-5 rounded-xl border border-border-strong/30 bg-accent/5 flex flex-col gap-4",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h3", {
							className: "text-xs font-mono font-bold uppercase tracking-wider text-accent",
							children: "Authentification Plex"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "text-xs text-text-2 leading-relaxed",
							children: "Connectez Vigile à votre compte Plex pour activer la détection et les diagnostics automatiques de charge."
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
							className: "flex flex-wrap items-center gap-3",
							children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
								onClick: handleConnectPlex,
								disabled: plexConnecting,
								className: "flex items-center gap-1.5 px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wider bg-orange-500 hover:bg-orange-600 text-white rounded-lg transition-colors cursor-pointer disabled:opacity-50",
								children: [plexConnecting ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "animate-spin rounded-full h-3.5 w-3.5 border-t-2 border-white border-zinc-800" }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Package, { className: "w-4 h-4" }), "Lier Plex"]
							}), plexPinCode && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex items-center gap-2",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-xs text-text-3 font-mono",
									children: "CODE:"
								}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("code", {
									className: "text-sm font-mono font-bold bg-surface-3 px-2 py-0.5 rounded text-accent tracking-wider animate-pulse border border-accent/25",
									children: plexPinCode
								})]
							})]
						})
					]
				})]
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "lg:col-span-2",
				children: [
					plexLoadingData && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-col items-center justify-center py-20 bg-zinc-900/10 rounded-xl border border-zinc-800/40",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "animate-spin rounded-full h-10 w-10 border-t-2 border-orange-500 border-zinc-800 mb-4" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "text-zinc-500 text-sm font-mono",
							children: "Analyse de Plex en cours..."
						})]
					}),
					!plexLoadingData && !selectedNodeId && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "flex flex-col items-center justify-center py-16 bg-zinc-900/10 rounded-xl border border-zinc-800/40 text-center px-6",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, { className: "w-10 h-10 text-zinc-500 mb-3" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
							className: "text-zinc-400 text-sm font-mono",
							children: "Veuillez sélectionner un serveur pour inspecter Plex."
						})]
					}),
					!plexLoadingData && selectedNodeId && plexDetection && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "space-y-6",
						children: [
							!plexDetection.detected ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex items-center gap-3 p-4 bg-severity-warning/10 border border-severity-warning/20 rounded-xl text-severity-warning",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(TriangleAlert, { className: "w-5 h-5 shrink-0" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-sm font-semibold",
									children: "Plex Media Server n'a pas été détecté sur ce nœud (aucun processus ni conteneur docker trouvé)."
								})]
							}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "flex items-center justify-between p-4 bg-severity-ok/10 border border-severity-ok/20 rounded-xl text-severity-ok",
								children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
									className: "flex items-center gap-2",
									children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CircleCheck, { className: "w-5 h-5 shrink-0" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
										className: "text-sm font-semibold",
										children: [
											"Plex détecté sur le port ",
											/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
												className: "font-bold",
												children: plexDetection.port
											}),
											" (",
											plexDetection.type,
											")"
										]
									})]
								}), plexDetection.status && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
									className: "text-[10px] font-bold font-mono bg-severity-ok/25 text-severity-ok px-2.5 py-0.5 rounded-full uppercase",
									children: plexDetection.status
								})]
							}),
							plexDetection.detected && !plexDetection.configured && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
								className: "p-4 bg-severity-warning/5 border border-severity-warning/15 rounded-xl text-text-2 text-xs leading-relaxed",
								children: "⚠️ Le token d'authentification Plex n'est pas configuré. Veuillez utiliser le bouton de connexion ci-contre pour lier Vigile."
							}),
							plexDetection.detected && plexDetection.configured && /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
								className: "p-5 rounded-xl border border-border-strong/30 bg-surface-2/10 backdrop-blur-xs flex flex-col gap-4",
								children: [
									/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
										className: "flex border-b border-border-strong/10 gap-4",
										children: [
											"sessions",
											"libraries",
											"users"
										].map((tab) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("button", {
											onClick: () => setPlexActiveTab(tab),
											className: `pb-2.5 text-xs font-bold uppercase tracking-wider transition-colors cursor-pointer border-b-2 ${plexActiveTab === tab ? "text-orange-500 border-orange-500" : "text-text-3 border-transparent hover:text-text-2"}`,
											children: [
												tab === "sessions" && "Lectures en cours",
												tab === "libraries" && "Bibliothèques",
												tab === "users" && "Utilisateurs"
											]
										}, tab))
									}),
									plexActiveTab === "sessions" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PlexSessionsTab, { sessions: plexSessions }),
									plexActiveTab === "libraries" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PlexLibrariesTab, { libraries: plexLibraries }),
									plexActiveTab === "users" && /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PlexUsersTab, { users: plexUsers })
								]
							})
						]
					})
				]
			})]
		})]
	});
};
//#endregion
export { PlexAdmin, PlexAdmin as default };
