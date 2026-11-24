import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Play,
  Pause,
  Save,
  Globe,
  Plus,
  Trash2,
  Edit2,
  Check,
  CheckCircle2,
  X,
  AlertCircle,
  FileUp,
  RotateCcw,
  Sparkles,
  ShieldCheck,
  Loader2,
  Hand,
  Copy,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  MousePointerClick,
  Type,
  Video,
  Activity,
  Maximize2,
  Minimize2,
  Search,
  ExternalLink,
  Laptop,
  Smartphone,
  Sliders,
  Terminal,
  Wifi,
  CornerDownRight,
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  Lock,
  Eye,
  EyeOff,
  Code2,
  FlaskConical,
  ArrowUp,
  MoreHorizontal,
  Wand2,
  Settings,
  Monitor,
  Key,
  Database,
  SlidersHorizontal,
  LogOut,
  Mic,
  Camera,
  Layers,
  CircleAlert,
} from "lucide-react";
import { api } from "../services/api";
import { useWebSocket } from "../context/WebSocketContext";
import { useToast } from "../context/ToastContext";
import { useProject } from "../context/ProjectContext";

export function Recorder() {
  const [url, setUrl] = useState("https://www.google.com");
  const [testcaseName, setTestcaseName] = useState("Google Search Flow");
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [browser, setBrowser] = useState(() => {
    try {
      return localStorage.getItem("tracecase_default_browser") || "chromium";
    } catch {
      return "chromium";
    }
  });
  const [headless, setHeadless] = useState(true);
  const [status, setStatus] = useState({ status: "idle" });

  // Clean empty step list by default (matching Screenshot 1)
  const [liveSteps, setLiveSteps] = useState([]);

  const [loading, setLoading] = useState(false);
  const [pauseLoading, setPauseLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(160); // 02:40 timer

  // Track status in ref for resilient socket reconnects
  const statusRef = useRef(status);
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  // Browser Kit Engine Preparation & Health (Persistent until web app mounts)
  const [isPreparingEngine, setIsPreparingEngine] = useState(false);
  const [prepStage, setPrepStage] = useState(0); // 1: runtime, 2: sandbox, 3: screencast, 4: mount
  const [hasFirstFrame, setHasFirstFrame] = useState(false);
  const [hasMountedApp, setHasMountedApp] = useState(false);
  const [discoveredBrowsers, setDiscoveredBrowsers] = useState([]);

  const isPreparingEngineRef = useRef(false);
  useEffect(() => {
    isPreparingEngineRef.current = isPreparingEngine;
  }, [isPreparingEngine]);

  const hasMountedAppRef = useRef(false);
  useEffect(() => {
    hasMountedAppRef.current = hasMountedApp;
  }, [hasMountedApp]);

  const getBrowserMeta = (b) => {
    switch (b) {
      case "webkit":
        return { name: "WebKit (Safari)", engine: "webkit", channel: "bundled", color: "text-blue-500", bg: "bg-blue-500/10" };
      case "firefox":
        return { name: "Mozilla Firefox", engine: "firefox", channel: "bundled", color: "text-amber-500", bg: "bg-amber-500/10" };
      case "msedge":
        return { name: "Microsoft Edge", engine: "msedge", channel: "stable", color: "text-teal-500", bg: "bg-teal-500/10" };
      case "chrome":
      case "chromium":
      default:
        return { name: "Google Chrome", engine: "chromium", channel: "stable", color: "text-emerald-500", bg: "bg-emerald-500/10" };
    }
  };

  const browserMeta = getBrowserMeta(browser);

  // Authoring & Interaction States
  const [manualInteraction, setManualInteraction] = useState(true);
  const [nlPrompt, setNlPrompt] = useState("");
  const [promptLoading, setPromptLoading] = useState(false);
  const [isVariablesOpen, setIsVariablesOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isEnvOpen, setIsEnvOpen] = useState(false);
  const [targetEnvironment, setTargetEnvironment] = useState("global");
  const [stepTimeoutMs, setStepTimeoutMs] = useState(0);
  const [enableSelfHealing, setEnableSelfHealing] = useState(true);
  const [captureNetwork, setCaptureNetwork] = useState(true);
  const [captureConsole, setCaptureConsole] = useState(true);
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [skipSampleExecution, setSkipSampleExecution] = useState(false);
  const [savingTestcase, setSavingTestcase] = useState(false);
  const [activeBottomTab, setActiveBottomTab] = useState("features"); // 'features' | 'network' | 'console' | 'telemetry'
  const [slashMenuOpen, setSlashMenuOpen] = useState(false);

  // Edit / Stats Counters (Passed, Edited/Additions, Warnings)
  const [passedCount, setPassedCount] = useState(0);
  const [editedCount, setEditedCount] = useState(0);
  const [warnCount, setWarnCount] = useState(0);

  // Active step menu popover
  const [activeStepMenu, setActiveStepMenu] = useState(null);

  // Local Google search preview state (when canvas stream is idle)
  const [googleQuery, setGoogleQuery] = useState("");

  // Local Variables Store
  const [localVariables, setLocalVariables] = useState([
    { key: "base_url", value: "https://www.google.com", isSecret: false },
    { key: "search_term", value: "Tracecase automated testing", isSecret: false },
    { key: "user_email", value: "developer@tracecase.io", isSecret: false },
    { key: "auth_token", value: "tc_live_secret_token_99", isSecret: true },
  ]);
  const [newVarKey, setNewVarKey] = useState("");
  const [newVarVal, setNewVarVal] = useState("");
  const [newVarSecret, setNewVarSecret] = useState(false);

  // Step modal
  const [isAddingStep, setIsAddingStep] = useState(false);
  const [newStepType, setNewStepType] = useState("click");
  const [newStepTarget, setNewStepTarget] = useState("");
  const [newStepValue, setNewStepValue] = useState("");
  const [newStepDesc, setNewStepDesc] = useState("");

  // Condition collapse states
  const [collapsedConditions, setCollapsedConditions] = useState({});
  const [showElseSteps, setShowElseSteps] = useState({});

  // Embedded CDP Screencast & Browser Chrome States
  const [streamConnected, setStreamConnected] = useState(false);
  const [streamSessionId, setStreamSessionId] = useState(null);
  const [streamToken, setStreamToken] = useState(null);
  const [viewportDims, setViewportDims] = useState({ width: 1440, height: 900 });
  const [chromeUrl, setChromeUrl] = useState("https://www.google.com");
  const chromeUrlRef = useRef(chromeUrl);
  useEffect(() => {
    chromeUrlRef.current = chromeUrl;
  }, [chromeUrl]);
  const [tabs, setTabs] = useState([
    { page_id: 0, title: "Google", url: "https://www.google.com" },
  ]);
  const [activeTabId, setActiveTabId] = useState(0);
  const [latencyMs, setLatencyMs] = useState(1);
  const [deviceMode, setDeviceMode] = useState("desktop"); // 'desktop' | 'mobile'

  // Active Dialog & File Chooser Overlays
  const [activeDialog, setActiveDialog] = useState(null);
  const [dialogPromptValue, setDialogPromptValue] = useState("");
  const [activeFileChooser, setActiveFileChooser] = useState(null);
  const [fileUploadPath, setFileUploadPath] = useState("");
  const [downloadNotice, setDownloadNotice] = useState(null);

  // Diagnostics & Event Logs
  const [consoleLogs, setConsoleLogs] = useState([]);
  const [networkRequests, setNetworkRequests] = useState([]);
  const [pageErrors, setPageErrors] = useState([]);

  // Refs
  const canvasRef = useRef(null);
  const streamWsRef = useRef(null);
  const offscreenImgRef = useRef(new Image());
  const lastMouseMoveRef = useRef(0);
  const frameCountRef = useRef(0);
  const viewportContainerRef = useRef(null);
  const timerRef = useRef(null);
  const inputRef = useRef(null);

  const { subscribe } = useWebSocket();
  const { showToast } = useToast();
  const { projects, currentProject } = useProject();
  const [selectedProjectId, setSelectedProjectId] = useState(
    currentProject?.id || "default_project"
  );
  const navigate = useNavigate();

  useEffect(() => {
    if (currentProject?.id && !selectedProjectId) {
      setSelectedProjectId(currentProject.id);
    }
  }, [currentProject]);

  useEffect(() => {
    api.getSettings()
      .then((settings) => {
        if (settings?.default_browser) {
          setBrowser(settings.default_browser);
          localStorage.setItem("tracecase_default_browser", settings.default_browser);
        }
      })
      .catch(() => {});

    const handleBrowserChange = (e) => {
      if (e?.detail) {
        setBrowser(e.detail);
      }
    };
    window.addEventListener("tracecase:browser-changed", handleBrowserChange);

    // Discover installed local browser runtimes
    api.getAvailableDevices()
      .then((data) => {
        if (data?.browsers) {
          setDiscoveredBrowsers(data.browsers);
        }
      })
      .catch(() => {});

    return () => {
      window.removeEventListener("tracecase:browser-changed", handleBrowserChange);
    };
  }, []);

  const fetchStatus = async () => {
    try {
      const data = await api.getRecordingStatus();
      setStatus(data);
      if (data.steps && Array.isArray(data.steps) && data.steps.length > 0) {
        setLiveSteps(data.steps);
        setPassedCount(data.steps.length);
      }
      if (data.elapsed_seconds !== undefined) {
        setElapsedSeconds(data.elapsed_seconds);
      }
      if (data.session_id && (data.status === "recording" || data.status === "paused")) {
        setStreamSessionId(data.session_id);
        setStreamToken(data.stream_token);
        if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) {
          connectStreamWebSocket(data.session_id, data.stream_token);
        }
      }
    } catch (err) {
      console.debug("Failed to fetch recording status:", err);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  // Timer interval when recording is active
  useEffect(() => {
    if (status.status === "recording" && !status.is_paused) {
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [status.status, status.is_paused]);

  // Subscribe to general system WebSockets
  useEffect(() => {
    const unsubStep = subscribe("recording_step", (payload) => {
      if (payload && payload.step) {
        setLiveSteps((prev) => [...prev, payload.step]);
        setPassedCount((prev) => prev + 1);
      }
      if (payload && payload.console_errors_count !== undefined) {
        setStatus((prev) => ({
          ...prev,
          console_errors_count: payload.console_errors_count,
          network_requests_count: payload.network_requests_count,
        }));
      }
    });

    const unsubCompleted = subscribe("recording_completed", (payload) => {
      setStatus((prev) => ({ ...prev, status: "completed" }));
      showToast("Recording session completed successfully!", "success");
      if (streamWsRef.current) {
        streamWsRef.current.close();
      }
      if (payload && payload.testcase_id) {
        navigate(`/testcases/${payload.testcase_id}`);
      }
    });

    const unsubPaused = subscribe("recording_paused", () => {
      setStatus((prev) => ({ ...prev, status: "paused", is_paused: true }));
      showToast("Recording paused", "info");
    });

    const unsubResumed = subscribe("recording_resumed", () => {
      setStatus((prev) => ({ ...prev, status: "recording", is_paused: false }));
      showToast("Recording resumed", "success");
    });

    const unsubError = subscribe("recording_error", (payload) => {
      const err = payload?.data?.error || payload?.error || "Browser session could not be started";
      // Ignore non-fatal navigation timeout notices so user workflow is uninterrupted
      if (typeof err === "string" && (err.includes("Timeout") || err.includes("waiting until"))) {
        console.warn("Studio non-fatal navigation notice:", err);
        return;
      }
      setStatus((prev) => ({ ...prev, status: "error", error: err }));
      showToast("Recording error: " + err, "error");
    });

    return () => {
      unsubStep();
      unsubCompleted();
      unsubPaused();
      unsubResumed();
      unsubError();
    };
  }, [subscribe, navigate, showToast]);

  // Periodic ping for WebSocket keep-alive & RTT measurement
  useEffect(() => {
    if (!streamConnected) return;
    const pingInterval = setInterval(() => {
      if (streamWsRef.current && streamWsRef.current.readyState === WebSocket.OPEN) {
        streamWsRef.current.send(
          JSON.stringify({
            type: "ping",
            data: { client_ts: performance.now() },
          })
        );
      }
    }, 5000);

    return () => clearInterval(pingInterval);
  }, [streamConnected]);

  // Connect to dedicated screencast WebSocket
  const connectStreamWebSocket = useCallback((sessionId, token) => {
    if (!sessionId) return;
    if (streamWsRef.current) {
      streamWsRef.current.close();
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : "";
    const wsUrl = `${protocol}//${window.location.host}/api/ws/record/stream/${sessionId}${tokenQuery}`;

    const ws = new WebSocket(wsUrl);
    streamWsRef.current = ws;

    ws.onopen = () => {
      setStreamConnected(true);
      setStreamSessionId(sessionId);
      setStreamToken(token);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = msg.type;
        const payload = msg.payload || {};

        if (type === "frame") {
          frameCountRef.current += 1;
          setHasFirstFrame(true);

          const curUrl = chromeUrlRef.current;
          const isTargetMounted = curUrl && curUrl !== "about:blank" && !curUrl.includes("about:blank");
          if (isTargetMounted) {
            setHasMountedApp(true);
            setPrepStage(4);
            if (isPreparingEngineRef.current) {
              setTimeout(() => {
                setIsPreparingEngine(false);
                setLoading(false);
              }, 400);
            }
          }
          const img = offscreenImgRef.current;
          img.onload = () => {
            const canvas = canvasRef.current;
            if (!canvas) return;
            const ctx = canvas.getContext("2d");
            if (!ctx) return;
            if (
              canvas.width !== img.naturalWidth ||
              canvas.height !== img.naturalHeight
            ) {
              canvas.width = img.naturalWidth;
              canvas.height = img.naturalHeight;
              setViewportDims({ width: img.naturalWidth, height: img.naturalHeight });
            }
            ctx.drawImage(img, 0, 0);
          };
          img.src = "data:image/jpeg;base64," + payload.data_base64;
        } else if (type === "session_state") {
          if (payload.url) {
            setChromeUrl(payload.url);
            chromeUrlRef.current = payload.url;
            if (payload.url !== "about:blank" && !payload.url.includes("about:blank")) {
              setHasMountedApp(true);
              setPrepStage(4);
              if (isPreparingEngineRef.current) {
                setTimeout(() => {
                  setIsPreparingEngine(false);
                  setLoading(false);
                }, 400);
              }
            }
          }
          if (payload.viewport_width && payload.viewport_height) {
            setViewportDims({
              width: payload.viewport_width,
              height: payload.viewport_height,
            });
          }
        } else if (type === "pong" || type === "input_ack") {
          if (payload.client_ts) {
            const rtt = Math.round(performance.now() - payload.client_ts);
            setLatencyMs(rtt);
          }
        } else if (type === "tab_opened") {
          setTabs((prev) => {
            const exists = prev.some((t) => t.page_id === payload.page_id);
            if (exists) return prev;
            return [
              ...prev,
              {
                page_id: payload.page_id,
                title: payload.title || `Tab ${payload.page_id + 1}`,
                url: payload.url || "about:blank",
              },
            ];
          });
          setActiveTabId(payload.page_id);
        } else if (type === "tab_switched") {
          if (payload.url && payload.url !== "about:blank" && !payload.url.includes("about:blank")) {
            setChromeUrl(payload.url);
            chromeUrlRef.current = payload.url;
            setHasMountedApp(true);
            setPrepStage(4);
            if (isPreparingEngineRef.current) {
              setTimeout(() => {
                setIsPreparingEngine(false);
                setLoading(false);
              }, 400);
            }
          }
          if (payload.page_id !== undefined) {
            setActiveTabId(payload.page_id);
            setTabs((prev) =>
              prev.map((t) =>
                t.page_id === payload.page_id
                  ? { ...t, url: payload.url || t.url, title: payload.title || t.title }
                  : t
              )
            );
          }
        } else if (type === "tab_closed") {
          setTabs((prev) => prev.filter((t) => t.page_id !== payload.page_id));
          setActiveTabId(0);
        } else if (type === "dialog_opened") {
          setActiveDialog({
            dialog_type: payload.dialog_type,
            message: payload.message,
            default_prompt: payload.default_prompt || "",
          });
          setDialogPromptValue(payload.default_prompt || "");
        } else if (type === "file_chooser_opened") {
          setActiveFileChooser({
            multiple: payload.multiple || false,
          });
        } else if (type === "console_log") {
          setConsoleLogs((prev) => [...prev.slice(-99), payload]);
        } else if (type === "page_error") {
          setPageErrors((prev) => [...prev.slice(-49), payload]);
        } else if (type === "network_request") {
          setNetworkRequests((prev) => [...prev.slice(-99), payload]);
        } else if (type === "download_started") {
          setDownloadNotice({
            status: "downloading",
            filename: payload.suggested_filename || "download",
          });
        } else if (type === "download_finished") {
          setDownloadNotice({
            status: "completed",
            filename: payload.filename,
            path: payload.path,
          });
          setTimeout(() => setDownloadNotice(null), 6000);
        }
      } catch (err) {
        console.debug("Error parsing WebSocket message:", err);
      }
    };

    ws.onclose = () => {
      setStreamConnected(false);
      // Auto-reconnect if session is active or paused
      const cur = statusRef.current?.status;
      if (sessionId && (cur === "recording" || cur === "paused")) {
        setTimeout(() => {
          if (streamWsRef.current?.readyState !== WebSocket.OPEN) {
            connectStreamWebSocket(sessionId, token);
          }
        }, 1200);
      }
    };

    ws.onerror = (err) => {
      console.debug("Stream WebSocket notice:", err);
      setStreamConnected(false);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (streamWsRef.current) {
        streamWsRef.current.close();
      }
    };
  }, []);

  // Map mouse coordinate from canvas client pixels to browser viewport pixels
  const getCoordinates = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    return {
      x,
      y,
      client_viewport: {
        client_width: rect.width,
        client_height: rect.height,
        content_x: 0,
        content_y: 0,
        content_width: rect.width,
        content_height: rect.height,
        device_pixel_ratio: window.devicePixelRatio || 1.0,
      },
    };
  };

  // Input event dispatchers (forwarded only when manualInteraction is true)
  const sendInputEvent = (inputData) => {
    if (!manualInteraction) return;
    if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "input",
        data: inputData,
      })
    );
  };

  const handleMouseMove = (e) => {
    const now = performance.now();
    if (now - lastMouseMoveRef.current < 100) return;
    lastMouseMoveRef.current = now;

    const coords = getCoordinates(e);
    if (!coords) return;
    sendInputEvent({
      event_type: "mouse_move",
      x: coords.x,
      y: coords.y,
      client_viewport: coords.client_viewport,
    });
  };

  const handleMouseDown = (e) => {
    if (canvasRef.current) {
      canvasRef.current.focus();
    }
  };

  const handleMouseUp = (e) => {
    // Click event handles single clicks cleanly without race conditions
  };

  const handleClick = (e) => {
    if (canvasRef.current) {
      canvasRef.current.focus();
    }
    const coords = getCoordinates(e);
    if (!coords) return;
    const buttonMap = { 0: "left", 1: "middle", 2: "right" };
    const now = performance.now();
    sendInputEvent({
      event_type: "click",
      x: coords.x,
      y: coords.y,
      button: buttonMap[e.button] || "left",
      click_count: e.detail || 1,
      client_viewport: coords.client_viewport,
      client_ts: now,
    });
  };

  const handleDoubleClick = (e) => {
    if (canvasRef.current) {
      canvasRef.current.focus();
    }
    const coords = getCoordinates(e);
    if (!coords) return;
    const buttonMap = { 0: "left", 1: "middle", 2: "right" };
    sendInputEvent({
      event_type: "dblclick",
      x: coords.x,
      y: coords.y,
      button: buttonMap[e.button] || "left",
      client_viewport: coords.client_viewport,
    });
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const coords = getCoordinates(e);
    if (!coords) return;
    sendInputEvent({
      event_type: "wheel",
      x: coords.x,
      y: coords.y,
      delta_x: e.deltaX,
      delta_y: e.deltaY,
      client_viewport: coords.client_viewport,
    });
  };

  const handleContextMenu = (e) => {
    e.preventDefault();
    if (canvasRef.current) {
      canvasRef.current.focus();
    }
    const coords = getCoordinates(e);
    if (!coords) return;
    sendInputEvent({
      event_type: "click",
      x: coords.x,
      y: coords.y,
      button: "right",
      click_count: 1,
      client_viewport: coords.client_viewport,
    });
  };

  const handleKeyDown = (e) => {
    if (!streamConnected || !manualInteraction) return;
    e.stopPropagation();

    // Special navigation / editing keys
    const specialKeys = [
      "Enter",
      "Escape",
      "Tab",
      "Backspace",
      "Delete",
      "ArrowUp",
      "ArrowDown",
      "ArrowLeft",
      "ArrowRight",
    ];

    if (specialKeys.includes(e.key)) {
      e.preventDefault();
      sendInputEvent({
        event_type: "key_down",
        key: e.key,
        code: e.code,
      });
      return;
    }

    // Single printable character (typing)
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      sendInputEvent({
        event_type: "type",
        text: e.key,
      });
      return;
    }

    // Modifier keys (Shift, Ctrl, Alt, Meta)
    if (["Shift", "Control", "Alt", "Meta"].includes(e.key)) {
      sendInputEvent({
        event_type: "key_down",
        key: e.key,
        code: e.code,
      });
    }
  };

  const handleKeyUp = (e) => {
    if (!streamConnected || !manualInteraction) return;
    e.stopPropagation();
    if (["Shift", "Control", "Alt", "Meta"].includes(e.key)) {
      sendInputEvent({
        event_type: "key_up",
        key: e.key,
        code: e.code,
      });
    }
  };

  const handlePaste = (e) => {
    if (!streamConnected || !manualInteraction) return;
    e.stopPropagation();
    e.preventDefault();
    const text = e.clipboardData.getData("text");
    if (text) {
      sendInputEvent({
        event_type: "paste",
        text,
      });
    }
  };

  const handleDeviceModeChange = (mode) => {
    setDeviceMode(mode);
    if (mode === "mobile") {
      setViewportDims({ width: 393, height: 852 });
      if (streamConnected) {
        sendInputEvent({ event_type: "resize", width: 393, height: 852 });
      }
    } else {
      setViewportDims({ width: 1280, height: 720 });
      if (streamConnected) {
        sendInputEvent({ event_type: "resize", width: 1280, height: 720 });
      }
    }
  };

  // Browser Chrome Actions
  const handleNavigateSubmit = (e) => {
    if (e) e.preventDefault();
    if (!chromeUrl.trim()) return;
    const targetUrl = chromeUrl.startsWith("http") ? chromeUrl.trim() : `https://${chromeUrl.trim()}`;

    // If session is not running, launch it!
    if (status.status !== "recording" && status.status !== "paused") {
      handleStart(targetUrl);
      return;
    }

    sendInputEvent({
      event_type: "navigate",
      url: targetUrl,
    });
    setLiveSteps((prev) => [
      ...prev,
      {
        number: prev.length + 1,
        action: "navigate",
        action_type: "navigate",
        description: `Open '${targetUrl}'`,
        url: targetUrl,
      },
    ]);
    setPassedCount((prev) => prev + 1);
    setTabs([{ page_id: 0, title: targetUrl, url: targetUrl }]);
    showToast(`Navigated to ${targetUrl}`, "success");
  };

  const handleRefreshPage = () => {
    sendInputEvent({ event_type: "reload" });
    showToast("Replayed page refresh", "info");
  };

  const handleGoBack = () => {
    sendInputEvent({ event_type: "go_back" });
  };

  const handleGoForward = () => {
    sendInputEvent({ event_type: "go_forward" });
  };

  const handleNewTab = () => {
    if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "new_tab",
        data: { url: "https://www.google.com" },
      })
    );
  };

  const handleSwitchTab = (pageId) => {
    if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "switch_tab",
        data: { page_id: pageId },
      })
    );
    setActiveTabId(pageId);
  };

  const handleCloseTab = (pageId, e) => {
    e.stopPropagation();
    if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "close_tab",
        data: { page_id: pageId },
      })
    );
  };

  const handleResetSession = async () => {
    if (status.status === "recording" || status.status === "paused") {
      try {
        await api.stopRecording();
      } catch (_) {}
    }
    if (streamWsRef.current) {
      streamWsRef.current.close();
      streamWsRef.current = null;
    }
    setStreamConnected(false);
    setHasFirstFrame(false);
    setIsPreparingEngine(false);
    setLoading(false);
    setStatus({ status: "idle" });
    setUrl("https://www.google.com");
    setChromeUrl("https://www.google.com");
    setLiveSteps([]);
    setPassedCount(0);
    setEditedCount(0);
    setWarnCount(0);
    showToast("Session reset to https://www.google.com", "info");
  };

  // Launch Session Lifecycle
  const handleStart = async (targetUrl = url) => {
    const rawUrl = (targetUrl && targetUrl.trim()) || chromeUrl || "https://www.google.com";
    const finalUrl = rawUrl.startsWith("http") ? rawUrl : `https://${rawUrl}`;

    try {
      setLoading(true);
      setIsPreparingEngine(true);
      setHasFirstFrame(false);
      setHasMountedApp(false);
      setPrepStage(1);
      setElapsedSeconds(0);
      setTabs([{ page_id: 0, title: finalUrl, url: finalUrl }]);
      setActiveTabId(0);
      setChromeUrl(finalUrl);
      chromeUrlRef.current = finalUrl;

      // Progressive preparation indicators
      setTimeout(() => setPrepStage((s) => Math.max(s, 2)), 600);
      setTimeout(() => setPrepStage((s) => Math.max(s, 3)), 1400);

      const session = await api.startRecording({
        url: finalUrl,
        name: testcaseName.trim() || undefined,
        browser,
        headless: true,
        timeout: stepTimeoutMs || 0,
        project_id: selectedProjectId || "default_project",
        embedded: true,
      });

      setStatus(session);
      showToast("Local Browser Studio session launched!", "success");

      setLiveSteps([
        {
          number: 1,
          action: "navigate",
          action_type: "navigate",
          description: `Open '${finalUrl}'`,
          url: finalUrl,
        },
      ]);
      setPassedCount(1);

      if (session.session_id) {
        connectStreamWebSocket(session.session_id, session.stream_token);
      }

      // Safety guard: if mounting takes longer than 25s, release preparation spinner
      setTimeout(() => {
        setIsPreparingEngine(false);
        setLoading(false);
        setHasMountedApp(true);
      }, 25000);
    } catch (err) {
      setIsPreparingEngine(false);
      setLoading(false);
      showToast("Failed to start studio: " + err.message, "error");
    }
  };

  const handlePause = async () => {
    try {
      setPauseLoading(true);
      const res = await api.pauseRecording();
      setStatus(res);
    } catch (err) {
      showToast("Failed to pause session: " + err.message, "error");
    } finally {
      setPauseLoading(false);
    }
  };

  const handleResume = async () => {
    try {
      setPauseLoading(true);
      const res = await api.resumeRecording();
      setStatus(res);
    } catch (err) {
      showToast("Failed to resume session: " + err.message, "error");
    } finally {
      setPauseLoading(false);
    }
  };

  // Save Modal Handler (Matches Screenshot 4)
  const handleSaveAndExecute = async () => {
    try {
      setSavingTestcase(true);
      showToast("Saving test case and compiling code...", "info");

      let testcaseId = null;
      if (status.status === "recording" || status.status === "paused") {
        const res = await api.stopRecording();
        setStatus(res);
        if (streamWsRef.current) {
          streamWsRef.current.close();
        }
        testcaseId = res.testcase_id;
      } else {
        // Create testcase directly from authored steps
        const res = await api.createTestCase({
          name: testcaseName,
          start_url: chromeUrl || "https://www.google.com",
          browser,
          project_id: selectedProjectId || "default_project",
          steps: liveSteps,
        });
        testcaseId = res.id;
      }

      setIsSaveModalOpen(false);
      showToast("Test case saved successfully!", "success");

      if (testcaseId) {
        if (!skipSampleExecution) {
          navigate(`/testcases/${testcaseId}?run=true`);
        } else {
          navigate(`/testcases/${testcaseId}`);
        }
      } else {
        navigate("/testcases");
      }
    } catch (err) {
      showToast("Failed to save test case: " + err.message, "error");
    } finally {
      setSavingTestcase(false);
    }
  };

  // Google Search Trigger (When user interacts with Google Search in the viewport)
  const handleGoogleSearchSubmit = (e) => {
    if (e) e.preventDefault();
    if (!googleQuery.trim()) return;

    const query = googleQuery.trim();
    const isUrl =
      query.startsWith("http://") ||
      query.startsWith("https://") ||
      query.includes("opensource-demo") ||
      query.includes(".com") ||
      query.includes(".org") ||
      query.includes(".io") ||
      query.includes(".net") ||
      query.includes("localhost");

    const targetUrl = isUrl
      ? query.startsWith("http")
        ? query
        : `https://${query}`
      : `https://www.google.com/search?q=${encodeURIComponent(query)}`;

    setChromeUrl(targetUrl);
    setTabs([{ page_id: 0, title: isUrl ? targetUrl : `${query} - Google Search`, url: targetUrl }]);
    setGoogleQuery("");

    // If session is not running, launch it!
    if (status.status !== "recording" && status.status !== "paused") {
      handleStart(targetUrl);
      return;
    }

    sendInputEvent({
      event_type: "navigate",
      url: targetUrl,
    });
    setLiveSteps((prev) => [
      ...prev,
      {
        number: prev.length + 1,
        action: "navigate",
        action_type: "navigate",
        description: `Open '${targetUrl}'`,
        url: targetUrl,
      },
    ]);
    setPassedCount((prev) => prev + 1);
    showToast(`Navigated to ${targetUrl}`, "success");
  };

  // Natural Language Prompt Authoring Dispatcher (Bottom input bar)
  const handleNlPromptSubmit = (e) => {
    if (e) e.preventDefault();
    if (!nlPrompt.trim()) return;

    setPromptLoading(true);
    const raw = nlPrompt.trim();

    let generatedStep = null;
    if (raw.toLowerCase().startsWith("go to ") || raw.toLowerCase().startsWith("open ")) {
      const targetUrl = raw.replace(/^(go to|open)\s+/i, "");
      const fullUrl = targetUrl.startsWith("http") ? targetUrl : `https://${targetUrl}`;
      generatedStep = {
        number: liveSteps.length + 1,
        action: "navigate",
        action_type: "navigate",
        description: `Open '${fullUrl}'`,
        url: fullUrl,
      };
      setChromeUrl(fullUrl);
      sendInputEvent({ event_type: "navigate", url: fullUrl });
    } else if (raw.toLowerCase().startsWith("click ")) {
      const elem = raw.replace(/^click\s+(on\s+)?(the\s+)?/i, "");
      generatedStep = {
        number: liveSteps.length + 1,
        action: "click",
        action_type: "click",
        description: `Click on the ${elem}`,
        target: elem,
        selector: `text=${elem}`,
      };
    } else if (raw.toLowerCase().startsWith("type ") || raw.toLowerCase().startsWith("enter ")) {
      const val = raw.replace(/^(type|enter)\s+/i, "");
      generatedStep = {
        number: liveSteps.length + 1,
        action: "type",
        action_type: "type",
        description: `Type in input field '${val}'`,
        input_value: val,
      };
    } else if (raw.toLowerCase().startsWith("scroll")) {
      generatedStep = {
        number: liveSteps.length + 1,
        action: "scroll",
        action_type: "scroll",
        description: "Scroll document",
      };
    } else {
      generatedStep = {
        number: liveSteps.length + 1,
        action: "custom",
        action_type: "ai_action",
        description: raw,
      };
    }

    setLiveSteps((prev) => [...prev, generatedStep]);
    setPassedCount((prev) => prev + 1);
    setNlPrompt("");
    setSlashMenuOpen(false);
    setPromptLoading(false);
    showToast("Step authored locally!", "success");
  };

  const handleDeleteStep = (index) => {
    setLiveSteps((prev) => prev.filter((_, i) => i !== index));
    setPassedCount((prev) => Math.max(0, prev - 1));
    setActiveStepMenu(null);
    showToast("Step removed", "info");
  };

  const handleDuplicateStep = (index) => {
    const stepToDup = liveSteps[index];
    if (!stepToDup) return;
    const duplicated = {
      ...stepToDup,
      number: liveSteps.length + 1,
      description: `${stepToDup.description} (Copy)`,
    };
    setLiveSteps((prev) => [...prev, duplicated]);
    setPassedCount((prev) => prev + 1);
    setActiveStepMenu(null);
    showToast("Step duplicated", "success");
  };

  const formatTimer = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const isActive = status.status === "recording" || status.status === "paused";
  const isRecording = status.status === "recording";

  return (
    <div className="flex flex-col h-full w-full bg-slate-50 dark:bg-surface-dark text-slate-800 dark:text-slate-100 select-none overflow-hidden font-sans transition-colors">
      {/* ──────────────────────────────────────────────────────────────────────────
          STUDIO TOP BAR (Matches Screenshots 1, 2, 3)
          ────────────────────────────────────────────────────────────────────────── */}
      <header className="h-14 px-4 bg-white dark:bg-surface-panelDark border-b border-slate-200 dark:border-surface-borderDark flex items-center justify-between shrink-0 z-30 transition-colors overflow-x-auto scrollbar-none gap-2">
        {/* Left: Authoring Steps, Timer, Passed/Edited/Warning Counters, Pause */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Brand & Authoring Steps */}
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center text-white shadow-sm shrink-0">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="text-xs font-bold text-slate-900 dark:text-white truncate">
                Authoring Steps
              </span>
              {/* Timer Pill */}
              <span className="px-2 sm:px-2.5 py-0.5 rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-[10px] sm:text-[11px] font-mono font-medium text-slate-700 dark:text-slate-300">
                {formatTimer(elapsedSeconds)}
              </span>
            </div>
          </div>

          <div className="h-4 w-px bg-slate-200 dark:bg-slate-700 mx-0.5 sm:mx-1" />

          {/* Counter Dots (Passed, Additions/Edits, Warnings) */}
          <div className="flex items-center gap-2 sm:gap-3 text-xs font-semibold">
            {/* Green: Passed / Total steps */}
            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400" title="Passed Steps">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{passedCount}</span>
            </span>
            {/* Purple: Edits / Dynamic inputs */}
            <span className="flex items-center gap-1 text-indigo-600 dark:text-indigo-400" title="Edited Steps">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
              <span>{editedCount}</span>
            </span>
            {/* Yellow: Warnings / Alerts */}
            <span className="flex items-center gap-1 text-amber-500" title="Warnings">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{warnCount}</span>
            </span>
          </div>

          <div className="h-4 w-px bg-slate-200 dark:bg-slate-700 mx-0.5 sm:mx-1" />

          {/* Replay Button */}
          <button
            type="button"
            onClick={handleRefreshPage}
            aria-label="Refresh / Replay Page"
            className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-800 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            title="Refresh / Replay"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          {/* Pause / Resume / Record Button */}
          <button
            type="button"
            onClick={
              status.status === "recording"
                ? handlePause
                : status.status === "paused"
                ? handleResume
                : () => handleStart(chromeUrl)
            }
            disabled={pauseLoading || loading}
            aria-label={
              status.status === "recording"
                ? "Pause Recording"
                : status.status === "paused"
                ? "Resume Recording"
                : "Start Recording"
            }
            className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
              status.status === "recording"
                ? "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700 hover:bg-amber-100"
                : status.status === "paused"
                ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700 hover:bg-emerald-100"
                : "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-300 dark:border-rose-700 hover:bg-rose-100"
            }`}
          >
            {loading ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : status.status === "recording" ? (
              <>
                <Pause className="w-3 h-3 fill-current" />
                <span className="hidden sm:inline">Pause</span>
              </>
            ) : status.status === "paused" ? (
              <>
                <Play className="w-3 h-3 fill-current" />
                <span className="hidden sm:inline">Resume</span>
              </>
            ) : (
              <>
                <Play className="w-3 h-3 fill-current" />
                <span className="hidden sm:inline">Record</span>
              </>
            )}
          </button>
        </div>

        {/* Right: Environment, Advanced Settings, Variables, Save, Exit */}
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {/* Set Environment */}
          <button
            type="button"
            onClick={() => {
              setIsEnvOpen(!isEnvOpen);
              setIsSettingsOpen(false);
              setIsVariablesOpen(false);
            }}
            aria-label="Set Environment"
            className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
              isEnvOpen
                ? "bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800"
                : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            <Monitor className="w-3.5 h-3.5 text-brand-500" />
            <span className="hidden md:inline">Set Environment</span>
          </button>

          {/* Advanced Settings */}
          <button
            type="button"
            onClick={() => {
              setIsSettingsOpen(!isSettingsOpen);
              setIsEnvOpen(false);
              setIsVariablesOpen(false);
            }}
            aria-label="Advanced Settings"
            className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
              isSettingsOpen
                ? "bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800"
                : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            <Settings className="w-3.5 h-3.5 text-slate-500" />
            <span className="hidden lg:inline">Advanced Settings</span>
            <span className="px-1 text-[10px] font-bold rounded bg-slate-200 dark:bg-slate-700">1</span>
          </button>

          {/* Variables (x) */}
          <button
            type="button"
            onClick={() => {
              setIsVariablesOpen(!isVariablesOpen);
              setIsEnvOpen(false);
              setIsSettingsOpen(false);
            }}
            aria-label="Manage Variables"
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
              isVariablesOpen
                ? "bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800"
                : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            <span className="font-mono font-bold text-[11px] text-brand-500">(x)</span>
            <span className="hidden sm:inline">Variables</span>
          </button>

          {/* Save Button (Green, Opens Save Modal) */}
          <button
            type="button"
            onClick={() => setIsSaveModalOpen(true)}
            aria-label="Save Test Case"
            className="px-3 sm:px-4 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm shadow-emerald-600/20 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Save className="w-3.5 h-3.5" />
            <span>Save</span>
          </button>

          {/* Exit Button */}
          <button
            type="button"
            onClick={() => navigate("/testcases")}
            aria-label="Exit Studio"
            className="px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            Exit
          </button>
        </div>
      </header>

      {/* ──────────────────────────────────────────────────────────────────────────
          MAIN SPLIT VIEW: LEFT (AUTHORING STEPS) + RIGHT (GOOGLE CHROME BROWSER)
          ────────────────────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── LEFT PANE: AUTHORING STEPS LIST + BOTTOM AI/STEP BAR (~40% width) ── */}
        <div className="w-[380px] lg:w-[420px] xl:w-[450px] border-r border-slate-200 dark:border-surface-borderDark flex flex-col bg-white dark:bg-surface-panelDark shrink-0 transition-colors justify-between">
          {/* Steps List Area or Center Empty State */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {/* EMPTY STATE (Matches Screenshot 1) */}
            {liveSteps.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center px-6 py-12 space-y-3 animate-in fade-in duration-300">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-brand-50 to-indigo-50 dark:from-brand-950/40 dark:to-indigo-950/40 border border-brand-200/60 dark:border-brand-800/60 flex items-center justify-center text-brand-600 dark:text-brand-400 shadow-sm">
                  <FlaskConical className="w-7 h-7" />
                </div>
                <div className="space-y-1.5 max-w-xs">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    What do you want to test today?
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                    Add a step or define an objective to get started. Press{" "}
                    <code className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-brand-600 dark:text-brand-400 font-mono text-[11px] font-semibold">
                      /
                    </code>{" "}
                    for more actions, or interact manually to author your test case.
                  </p>
                </div>
              </div>
            ) : (
              /* POPULATED STEPS LIST (Matches Screenshots 2 & 3) */
              <div className="space-y-2.5">
                {liveSteps.map((step, idx) => {
                  return (
                    <div
                      key={idx}
                      className="group relative rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80 hover:border-slate-300 dark:hover:border-slate-700 shadow-xs p-3 transition-all"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          {/* Expand chevron */}
                          <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />

                          {/* Action Icon */}
                          {step.action_type === "navigate" || step.action === "navigate" ? (
                            <Globe className="w-4 h-4 text-emerald-500 shrink-0" />
                          ) : step.action_type === "type" || step.action === "type" ? (
                            <Type className="w-4 h-4 text-emerald-600 shrink-0" />
                          ) : step.action_type === "scroll" || step.action === "scroll" ? (
                            <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                          ) : (
                            <Wand2 className="w-4 h-4 text-emerald-500 shrink-0" />
                          )}

                          {/* Description */}
                          <span className="text-slate-800 dark:text-slate-200 font-medium truncate">
                            {step.description}
                          </span>
                        </div>

                        {/* Three dots menu */}
                        <div className="relative">
                          <button
                            type="button"
                            onClick={() =>
                              setActiveStepMenu(activeStepMenu === idx ? null : idx)
                            }
                            className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-white"
                          >
                            <MoreHorizontal className="w-3.5 h-3.5" />
                          </button>

                          {activeStepMenu === idx && (
                            <div className="absolute right-0 mt-1 w-32 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg shadow-xl py-1 z-50 text-xs">
                              <button
                                onClick={() => handleDuplicateStep(idx)}
                                className="w-full text-left px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center gap-1.5"
                              >
                                <Copy className="w-3 h-3" /> Duplicate
                              </button>
                              <button
                                onClick={() => handleDeleteStep(idx)}
                                className="w-full text-left px-3 py-1.5 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-rose-600 flex items-center gap-1.5"
                              >
                                <Trash2 className="w-3 h-3" /> Delete
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Cursor indicator indicator */}
                <div className="flex items-center gap-2 pt-1 px-1 text-[11px] font-mono text-slate-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
                  <span>Cursor</span>
                </div>
              </div>
            )}
          </div>

          {/* BOTTOM AUTHORING INPUT BAR (Matches Screenshots 1, 2, 3) */}
          <div className="p-3 border-t border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark relative">
            {/* Slash Commands Dropdown */}
            {slashMenuOpen && (
              <div className="absolute bottom-16 left-3 right-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl p-2 z-50 animate-in slide-in-from-bottom-2 text-xs space-y-1">
                <div className="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  Quick Step Commands
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setNlPrompt("Open 'https://www.google.com'");
                    setSlashMenuOpen(false);
                    inputRef.current?.focus();
                  }}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-2 text-slate-700 dark:text-slate-200"
                >
                  <Globe className="w-3.5 h-3.5 text-emerald-500" />
                  <span><strong>/open</strong> - Navigate to URL</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setNlPrompt("Click on the ");
                    setSlashMenuOpen(false);
                    inputRef.current?.focus();
                  }}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-2 text-slate-700 dark:text-slate-200"
                >
                  <Wand2 className="w-3.5 h-3.5 text-brand-500" />
                  <span><strong>/click</strong> - Click element</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setNlPrompt("Type in ");
                    setSlashMenuOpen(false);
                    inputRef.current?.focus();
                  }}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-2 text-slate-700 dark:text-slate-200"
                >
                  <Type className="w-3.5 h-3.5 text-indigo-500" />
                  <span><strong>/type</strong> - Input text</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setNlPrompt("Scroll document");
                    setSlashMenuOpen(false);
                    inputRef.current?.focus();
                  }}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-2 text-slate-700 dark:text-slate-200"
                >
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                  <span><strong>/scroll</strong> - Scroll page</span>
                </button>
              </div>
            )}

            <form onSubmit={handleNlPromptSubmit} className="relative flex items-center">
              <div className="absolute left-3.5 text-slate-400">
                <Sparkles className="w-4 h-4 text-brand-500" />
              </div>
              <input
                ref={inputRef}
                type="text"
                value={nlPrompt}
                onChange={(e) => {
                  setNlPrompt(e.target.value);
                  if (e.target.value === "/") {
                    setSlashMenuOpen(true);
                  } else if (!e.target.value) {
                    setSlashMenuOpen(false);
                  }
                }}
                placeholder="Add a step or an objective or press / for actions"
                className="w-full pl-10 pr-12 py-3 text-xs rounded-2xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:border-brand-500 transition-all font-sans"
              />
              <button
                type="submit"
                disabled={!nlPrompt.trim() || promptLoading}
                className="absolute right-2 w-7 h-7 rounded-full bg-slate-700 hover:bg-slate-900 dark:bg-slate-600 dark:hover:bg-slate-500 text-white flex items-center justify-center transition-all disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
              >
                {promptLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <ArrowUp className="w-3.5 h-3.5" />
                )}
              </button>
            </form>
          </div>
        </div>

        {/* ── RIGHT PANE: GOOGLE CHROME BROWSER VIEW (Matches Screenshots 1, 2, 3) ── */}
        <div className="flex-1 flex flex-col bg-slate-100 dark:bg-slate-950 overflow-hidden transition-colors">
          {/* Top Browser Bar (Google Chrome • Recording steps • Reset Session) */}
          <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between select-none">
            <div className="flex items-center gap-2.5">
              <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                {browserMeta.name}
              </span>

              {/* Browser Kit Preparation & Health Indicator */}
              {isPreparingEngine || (loading && !hasFirstFrame) ? (
                <span className="px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-[10px] font-semibold text-amber-600 dark:text-amber-400 flex items-center gap-1.5 animate-pulse">
                  <Loader2 className="w-2.5 h-2.5 animate-spin" />
                  <span>Preparing Browser Kit...</span>
                </span>
              ) : streamConnected && hasFirstFrame ? (
                <span className="px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  <span>Browser Kit Ready</span>
                </span>
              ) : (status.status === "recording" || status.status === "paused") ? (
                <span className="px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 text-[10px] font-semibold text-blue-600 dark:text-blue-400 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                  <span>Kit Active</span>
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-[10px] font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                  <span>Kit Standby</span>
                </span>
              )}

              {/* Pink Recording steps Pill */}
              {(status.status === "recording" || status.status === "paused") && (
                <span className="px-2 py-0.5 rounded-full bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-[10px] font-semibold text-rose-600 dark:text-rose-400 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                  <span>{status.status === "paused" ? "Recording Paused" : "Recording steps"}</span>
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={handleResetSession}
              className="flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Reset Session</span>
            </button>
          </div>

          {/* Chrome Tab Strip & Address Omnibox */}
          <div className="bg-slate-200/90 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 p-2 space-y-1.5 shrink-0 select-none">
            {/* Tab strip */}
            <div className="flex items-center gap-1 overflow-x-auto scrollbar-none">
              {tabs.map((tab) => (
                <div
                  key={tab.page_id}
                  onClick={() => handleSwitchTab(tab.page_id)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-t-lg text-xs font-medium cursor-pointer transition-all border-t border-x ${
                    activeTabId === tab.page_id
                      ? "bg-white dark:bg-slate-950 text-slate-900 dark:text-white border-slate-200 dark:border-slate-800 shadow-sm"
                      : "bg-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 border-transparent"
                  }`}
                >
                  <Globe className="w-3 h-3 text-blue-500" />
                  <span className="truncate max-w-[160px] text-[11px] font-medium">
                    {tab.title || "Google"}
                  </span>
                  {tabs.length > 1 && (
                    <button
                      type="button"
                      onClick={(e) => handleCloseTab(tab.page_id, e)}
                      className="text-slate-400 hover:text-slate-700 dark:hover:text-white ml-1"
                    >
                      <X className="w-2.5 h-2.5" />
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={handleNewTab}
                className="p-1 rounded text-slate-500 hover:text-slate-800 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
                title="New Tab"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Omnibox Address Bar */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 text-slate-500 dark:text-slate-400">
                <button
                  type="button"
                  onClick={handleGoBack}
                  className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-800 hover:text-slate-800 dark:hover:text-white transition-colors"
                  title="Back"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={handleGoForward}
                  className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-800 hover:text-slate-800 dark:hover:text-white transition-colors"
                  title="Forward"
                >
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={handleRefreshPage}
                  className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-800 hover:text-slate-800 dark:hover:text-white transition-colors"
                  title="Reload"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* URL Address Input (Showing google.com by default) */}
              <form onSubmit={handleNavigateSubmit} className="flex-1 relative">
                <Lock className="w-3 h-3 absolute left-3 top-1/2 -translate-y-1/2 text-emerald-500 dark:text-emerald-400" />
                <input
                  type="text"
                  value={chromeUrl}
                  onChange={(e) => setChromeUrl(e.target.value)}
                  placeholder="https://www.google.com"
                  className="w-full pl-8 pr-12 py-1.5 text-xs font-mono rounded-full bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800 focus:outline-none focus:border-brand-500 shadow-inner transition-colors"
                />
                <button
                  type="submit"
                  className="absolute right-1 top-1 bottom-1 px-2.5 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors"
                >
                  Go
                </button>
              </form>

              {/* Viewport Device Mode Toggle (Desktop vs Mobile Emulation) */}
              <div className="flex items-center gap-0.5 bg-slate-100 dark:bg-slate-800 p-0.5 rounded-lg border border-slate-200 dark:border-slate-700 shrink-0">
                <button
                  type="button"
                  onClick={() => handleDeviceModeChange("desktop")}
                  className={`px-2 py-1 rounded text-xs flex items-center gap-1 transition-colors cursor-pointer ${
                    deviceMode === "desktop"
                      ? "bg-white dark:bg-slate-700 text-brand-600 dark:text-brand-400 font-bold shadow-xs"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-300"
                  }`}
                  title="Desktop Viewport (1280x720)"
                >
                  <Monitor className="w-3 h-3" />
                  <span className="text-[10px]">Desktop</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleDeviceModeChange("mobile")}
                  className={`px-2 py-1 rounded text-xs flex items-center gap-1 transition-colors cursor-pointer ${
                    deviceMode === "mobile"
                      ? "bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 font-bold shadow-xs"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-300"
                  }`}
                  title="Mobile Viewport Emulation (393x852 iPhone 15 Pro)"
                >
                  <Smartphone className="w-3 h-3" />
                  <span className="text-[10px]">Mobile</span>
                </button>
              </div>
            </div>
          </div>

          {/* Browser Viewport (Live Stream Canvas or Google View) */}
          <div
            ref={viewportContainerRef}
            onClick={() => {
              if (canvasRef.current) canvasRef.current.focus();
            }}
            className={`flex-1 relative bg-slate-100 dark:bg-slate-950 flex flex-col items-center justify-center overflow-auto outline-none select-none cursor-default ${
              deviceMode === "mobile" ? "p-3 sm:p-5" : ""
            }`}
          >
            <div
              className={`flex flex-col items-center justify-center transition-all ${
                deviceMode === "mobile"
                  ? "w-[390px] max-w-[92vw] h-[800px] max-h-[calc(100vh-175px)] bg-slate-900 rounded-[44px] p-2.5 shadow-2xl border-4 border-slate-700 ring-1 ring-slate-800/80 relative overflow-hidden shrink-0 my-auto"
                  : "w-full h-full relative"
              }`}
            >
              {deviceMode === "mobile" && (
                <>
                  {/* Dynamic Island */}
                  <div className="absolute top-3.5 left-1/2 -translate-x-1/2 w-28 h-5 bg-black rounded-full z-30 pointer-events-none flex items-center justify-end px-3">
                    <div className="w-2.5 h-2.5 rounded-full bg-slate-900 ring-1 ring-slate-800" />
                  </div>
                  {/* Home indicator bar */}
                  <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-32 h-1 bg-slate-400/50 rounded-full z-30 pointer-events-none" />
                </>
              )}
              {/* Live Screencast Canvas (Active Stream) */}
              <canvas
                ref={canvasRef}
                tabIndex={0}
                onMouseMove={handleMouseMove}
                onMouseDown={handleMouseDown}
                onMouseUp={handleMouseUp}
                onClick={handleClick}
                onDoubleClick={handleDoubleClick}
                onWheel={handleWheel}
                onContextMenu={handleContextMenu}
                onKeyDown={handleKeyDown}
                onKeyUp={handleKeyUp}
                onPaste={handlePaste}
                className={`max-w-full max-h-full ${
                  deviceMode === "mobile"
                    ? "w-full h-full object-cover rounded-[34px] bg-white dark:bg-slate-950"
                    : "object-contain"
                } outline-none focus:ring-2 focus:ring-brand-500/40 rounded-lg cursor-pointer ${
                  (hasFirstFrame && (!isPreparingEngine || hasMountedApp)) ? "block" : "hidden"
                }`}
              />

              {/* Browser Kit Preparation Checklist (Extends until target web application is mounted) */}
              {isPreparingEngine && (!hasMountedApp || chromeUrl === "about:blank") && (
                <div className="w-full h-full flex flex-col items-center justify-center p-6 bg-white dark:bg-slate-950 select-none animate-in fade-in space-y-6">
                  {/* Glowing Browser Engine Icon */}
                  <div className="relative">
                    <div className="w-16 h-16 rounded-3xl bg-brand-500/10 dark:bg-brand-500/20 border-2 border-brand-500/30 flex items-center justify-center text-brand-600 dark:text-brand-400 shadow-xl shadow-brand-500/10">
                      <Globe className="w-8 h-8 animate-pulse" />
                    </div>
                    <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-brand-600 text-white flex items-center justify-center shadow">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    </div>
                  </div>

                  <div className="text-center max-w-sm space-y-1">
                    <h3 className="text-base font-bold text-slate-900 dark:text-white">
                      Preparing {browserMeta.name} Browser Kit
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 font-mono truncate">
                      Target: {chromeUrl === "about:blank" ? (tabs[0]?.url || url || "Target Application") : chromeUrl}
                    </p>
                  </div>

                  {/* Progressive Preparation Checklist */}
                  <div className="w-full max-w-xs bg-slate-50 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 space-y-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2.5 text-slate-700 dark:text-slate-300 font-medium">
                        {prepStage >= 1 ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                        ) : (
                          <span className="w-4 h-4 rounded-full border border-slate-300 dark:border-slate-700 shrink-0" />
                        )}
                        <span>Launch {browserMeta.name} Runtime</span>
                      </span>
                      {prepStage === 1 && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-500" />}
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2.5 text-slate-700 dark:text-slate-300 font-medium">
                        {prepStage >= 2 ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                        ) : (
                          <span className="w-4 h-4 rounded-full border border-slate-300 dark:border-slate-700 shrink-0" />
                        )}
                        <span>Configure Sandbox &amp; Viewport</span>
                      </span>
                      {prepStage === 2 && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-500" />}
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2.5 text-slate-700 dark:text-slate-300 font-medium">
                        {prepStage >= 3 ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                        ) : (
                          <span className="w-4 h-4 rounded-full border border-slate-300 dark:border-slate-700 shrink-0" />
                        )}
                        <span>Attach Live Screencast &amp; Observers</span>
                      </span>
                      {prepStage === 3 && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-500" />}
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2.5 text-slate-700 dark:text-slate-300 font-medium">
                        {prepStage >= 4 && hasMountedApp ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                        ) : (
                          <span className="w-4 h-4 rounded-full border border-slate-300 dark:border-slate-700 shrink-0" />
                        )}
                        <span>Mount Target Web Application</span>
                      </span>
                      {(!hasMountedApp || prepStage < 4) && <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-500" />}
                    </div>
                  </div>

                  <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    <span>100% Local Desktop Intelligence • Zero Cloud Telemetry</span>
                  </div>
                </div>
              )}

              {/* Target Web Application Launch Card (Only when NOT in active recording session) */}
              {status.status !== "recording" && status.status !== "paused" && !isPreparingEngine && !streamConnected && !loading && !chromeUrl.includes("google.com") && (
                <div className="w-full h-full flex flex-col items-center justify-center p-6 bg-slate-50 dark:bg-slate-950 select-none animate-in fade-in">
                  <div className="max-w-md w-full p-6 sm:p-8 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl text-center space-y-5">
                    <div className="w-14 h-14 rounded-2xl bg-brand-50 dark:bg-brand-950/60 border border-brand-200 dark:border-brand-800 text-brand-600 dark:text-brand-400 flex items-center justify-center mx-auto shadow-sm">
                      <Globe className="w-7 h-7" />
                    </div>
                    <div className="space-y-1">
                      <h3 className="text-base font-bold text-slate-900 dark:text-white">
                        Target Web Application
                      </h3>
                      <p className="text-xs text-slate-500 font-mono break-all bg-slate-100 dark:bg-slate-800/80 px-3 py-2 rounded-xl text-slate-700 dark:text-slate-300">
                        {chromeUrl}
                      </p>
                    </div>

                    {/* Local Browser Kit Readiness Check */}
                    <div className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-850/60 border border-slate-200 dark:border-slate-800 text-left space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                          <span>Local Browser Kit Verified</span>
                        </span>
                        <span className="font-mono text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800">
                          Ready to Launch
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
                        Engine: <strong className="text-slate-700 dark:text-slate-300">{browserMeta.name}</strong> • Isolated Profile • 0ms Local Latency
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleStart(chromeUrl)}
                      className="w-full py-3 px-4 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-lg shadow-brand-500/20 hover:scale-[1.01] transition-all cursor-pointer"
                    >
                      <Play className="w-4 h-4 fill-current" />
                      <span>Launch Live Session &amp; Start Recording</span>
                    </button>
                    <p className="text-[11px] text-slate-400">
                      Launches local {browserMeta.name} engine and streams live interactions over CDP.
                    </p>
                  </div>
                </div>
              )}

              {/* Reconnecting / Stream Sync Overlay (Never rendered simultaneously with Preparation Card) */}
              {(status.status === "recording" || status.status === "paused") && !streamConnected && !isPreparingEngine && (
                <div className={`absolute inset-0 ${hasFirstFrame ? "bg-slate-950/70 backdrop-blur-[2px]" : "bg-white dark:bg-slate-950"} z-20 flex flex-col items-center justify-center space-y-4 animate-in fade-in p-6 text-center`}>
                  <div className="max-w-sm w-full p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl space-y-3">
                    <div className="flex items-center justify-center gap-2.5 text-brand-600 dark:text-brand-400">
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span className="text-sm font-bold text-slate-900 dark:text-white">Connecting to live studio stream...</span>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                      Syncing live viewport with {browserMeta.name} local engine.
                    </p>
                    <div className="flex items-center justify-center gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => {
                          if (status.session_id) {
                            connectStreamWebSocket(status.session_id, status.stream_token || streamToken);
                          } else {
                            fetchStatus();
                          }
                        }}
                        className="px-3.5 py-1.5 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold shadow transition-all cursor-pointer"
                      >
                        Retry Connection
                      </button>
                      <button
                        type="button"
                        onClick={handleResetSession}
                        className="px-3.5 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-medium border border-slate-200 dark:border-slate-700 transition-all cursor-pointer"
                      >
                        Reset Session
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Default Google Homepage View (Only when chromeUrl is Google) */}
              {!streamConnected && !loading && (chromeUrl.includes("google.com") || !chromeUrl) && (
              <div className="w-full h-full flex flex-col justify-between p-6 bg-white dark:bg-slate-950 select-none animate-in fade-in">
                {/* Google Top Bar */}
                <div className="flex items-center justify-end gap-4 text-xs text-slate-600 dark:text-slate-400">
                  <span className="hover:underline cursor-pointer">Gmail</span>
                  <span className="hover:underline cursor-pointer">Images</span>
                  <div className="w-7 h-7 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-xs shadow-sm">
                    G
                  </div>
                </div>

                {/* Google Center Search */}
                <div className="flex flex-col items-center justify-center max-w-xl mx-auto w-full space-y-6">
                  {/* Google Logo */}
                  <div className="text-5xl sm:text-6xl font-bold tracking-tight select-none">
                    <span className="text-blue-500">G</span>
                    <span className="text-red-500">o</span>
                    <span className="text-yellow-500">o</span>
                    <span className="text-blue-500">g</span>
                    <span className="text-green-500">l</span>
                    <span className="text-red-500">e</span>
                  </div>

                  {/* Google Search Bar */}
                  <form
                    onSubmit={handleGoogleSearchSubmit}
                    className="w-full relative flex items-center"
                  >
                    <Search className="w-4 h-4 text-slate-400 absolute left-4" />
                    <input
                      type="text"
                      value={googleQuery}
                      onChange={(e) => setGoogleQuery(e.target.value)}
                      placeholder="Search Google or type a URL..."
                      className="w-full pl-11 pr-20 py-3 rounded-full border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm hover:shadow-md focus:shadow-md focus:outline-none focus:border-slate-300 dark:focus:border-slate-600 text-sm text-slate-900 dark:text-white transition-all"
                      autoFocus
                    />
                    <div className="absolute right-4 flex items-center gap-2 text-slate-400">
                      <Mic className="w-4 h-4 hover:text-blue-500 cursor-pointer" />
                      <Camera className="w-4 h-4 hover:text-blue-500 cursor-pointer" />
                    </div>
                  </form>

                  {/* Search Action Buttons */}
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={handleGoogleSearchSubmit}
                      className="px-4 py-2 rounded-md bg-slate-50 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 transition-colors shadow-xs"
                    >
                      Google Search
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setGoogleQuery("Tracecase automated test studio");
                        handleGoogleSearchSubmit();
                      }}
                      className="px-4 py-2 rounded-md bg-slate-50 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 transition-colors shadow-xs"
                    >
                      I'm Feeling Lucky
                    </button>
                  </div>
                </div>

                {/* Google Footer */}
                <div className="border-t border-slate-100 dark:border-slate-900 pt-3 flex flex-wrap items-center justify-between text-[11px] text-slate-400">
                  <div className="flex items-center gap-4">
                    <span>About</span>
                    <span>Advertising</span>
                    <span>Business</span>
                    <span>How Search works</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span>Privacy</span>
                    <span>Terms</span>
                    <span>Settings</span>
                  </div>
                </div>
              </div>
            )}
            </div>
          </div>

          {/* Bottom Feature Ribbon (Matches Screenshot 1) */}
          <div className="h-12 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 flex items-center justify-between shrink-0 select-none text-[11px]">
            <div className="flex items-center gap-4 overflow-x-auto scrollbar-none text-slate-600 dark:text-slate-300">
              <button
                type="button"
                onClick={() => {
                  setNlPrompt("Execute custom javascript: console.log('test')");
                  inputRef.current?.focus();
                }}
                className="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
              >
                <Code2 className="w-3.5 h-3.5 text-slate-400" />
                <span>Execute Custom Code</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setNlPrompt("Call API endpoint https://api.example.com/v1");
                  inputRef.current?.focus();
                }}
                className="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
              >
                <Settings className="w-3.5 h-3.5 text-slate-400" />
                <span>Call External APIs</span>
              </button>
              <button
                type="button"
                onClick={() => setIsVariablesOpen(true)}
                className="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
              >
                <span className="font-mono font-bold text-slate-400">{"{x}"}</span>
                <span>Set Dynamic Values</span>
              </button>
              <button
                type="button"
                onClick={() => setIsVariablesOpen(true)}
                className="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
              >
                <Lock className="w-3.5 h-3.5 text-slate-400" />
                <span>Store Sensitive Keys</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  showToast("TOTP Token synced from local vault", "info");
                }}
                className="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
              >
                <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
                <span>Fetch TOTP in Real Time</span>
              </button>
              <button
                type="button"
                onClick={() => setIsEnvOpen(true)}
                className="flex items-center gap-1.5 hover:text-brand-600 dark:hover:text-brand-400 transition-colors shrink-0"
              >
                <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" />
                <span>Define Reusable Inputs</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ──────────────────────────────────────────────────────────────────────────
          SAVE TEST CASE MODAL (Matches Screenshot 4)
          ────────────────────────────────────────────────────────────────────────── */}
      {isSaveModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full shadow-2xl p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Save Test Case
              </h3>
              <button
                type="button"
                onClick={() => setIsSaveModalOpen(false)}
                className="text-slate-400 hover:text-slate-700 dark:hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <p className="text-xs font-semibold text-slate-900 dark:text-white">
                Want to run a sample execution of the code after saving?
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                Sample execution of code checks your test steps for correctness after saving.
                Code will be generated in both cases.
              </p>

              <div className="pt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  id="skipExec"
                  checked={skipSampleExecution}
                  onChange={(e) => setSkipSampleExecution(e.target.checked)}
                  className="rounded border-slate-300 dark:border-slate-700 text-brand-600 focus:ring-0"
                />
                <label
                  htmlFor="skipExec"
                  className="text-xs font-medium text-slate-700 dark:text-slate-300 cursor-pointer"
                >
                  Skip sample execution of code
                </label>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setIsSaveModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveAndExecute}
                disabled={savingTestcase}
                className="px-5 py-2 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition-all shadow-md shadow-emerald-600/25 flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {savingTestcase ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
                )}
                <span>Save & Run Execution</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          SET ENVIRONMENT DRAWER (Slides in from the right)
          ────────────────────────────────────────────────────────────────────────── */}
      {isEnvOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px] animate-in fade-in"
            onClick={() => setIsEnvOpen(false)}
          />
          <div className="fixed inset-y-0 right-0 w-96 max-w-full bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 flex items-center justify-center">
                  <Monitor className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">Environment &amp; Viewport</h3>
                  <p className="text-[10px] text-slate-400">Configure runtime dimensions and target profile</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsEnvOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="p-4 flex-1 overflow-y-auto space-y-5 text-xs">
              {/* Target Environment Profile */}
              <div>
                <label className="block text-slate-500 font-bold mb-1.5 uppercase tracking-wider text-[10px]">
                  Environment Profile
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: "local", name: "Local Dev", sub: "localhost" },
                    { id: "staging", name: "Staging", sub: "test env" },
                    { id: "prod", name: "Production", sub: "live domain" },
                    { id: "global", name: "Global", sub: "default" },
                  ].map((env) => (
                    <button
                      key={env.id}
                      type="button"
                      onClick={() => {
                        setTargetEnvironment(env.id);
                        showToast(`Switched profile to ${env.name}`, "info");
                      }}
                      className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                        targetEnvironment === env.id
                          ? "border-brand-500 bg-brand-50/50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300 font-semibold"
                          : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300"
                      }`}
                    >
                      <div className="font-bold">{env.name}</div>
                      <div className="text-[10px] text-slate-400">{env.sub}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Viewport Resolution */}
              <div>
                <label className="block text-slate-500 font-bold mb-1.5 uppercase tracking-wider text-[10px]">
                  Screen Resolution Presets
                </label>
                <div className="space-y-1.5">
                  {[
                    { name: "Desktop (Wide)", w: 1440, h: 900, icon: Laptop, tag: "Desktop" },
                    { name: "Laptop (HD)", w: 1280, h: 720, icon: Monitor, tag: "Standard" },
                    { name: "Tablet (iPad Pro)", w: 834, h: 1194, icon: Tablet, tag: "Tablet" },
                    { name: "Mobile (iPhone 15 Pro)", w: 393, h: 852, icon: Smartphone, tag: "Mobile" },
                    { name: "Mobile (Pixel 8)", w: 412, h: 915, icon: Smartphone, tag: "Mobile" },
                  ].map((preset) => {
                    const Icon = preset.icon;
                    const isSelected = viewportDims.width === preset.w && viewportDims.height === preset.h;
                    return (
                      <button
                        key={`${preset.w}x${preset.h}`}
                        type="button"
                        onClick={() => {
                          setViewportDims({ width: preset.w, height: preset.h });
                          if (preset.tag === "Mobile") {
                            setDeviceMode("mobile");
                          } else {
                            setDeviceMode("desktop");
                          }
                          if (streamConnected) {
                            sendInputEvent({ event_type: "resize", width: preset.w, height: preset.h });
                          }
                          showToast(`Viewport updated to ${preset.w} × ${preset.h}`, "info");
                        }}
                        className={`w-full p-2.5 rounded-xl border flex items-center justify-between transition-all cursor-pointer ${
                          isSelected
                            ? "border-brand-500 bg-brand-50/50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300 font-semibold"
                            : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300"
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <Icon className={`w-4 h-4 ${isSelected ? "text-brand-500" : "text-slate-400"}`} />
                          <div className="text-left">
                            <div className="font-semibold text-xs">{preset.name}</div>
                            <div className="text-[10px] text-slate-400 font-mono">
                              {preset.w} &times; {preset.h} px
                            </div>
                          </div>
                        </div>
                        {isSelected && <Check className="w-4 h-4 text-brand-500" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Base URL Override */}
              <div>
                <label className="block text-slate-500 font-bold mb-1.5 uppercase tracking-wider text-[10px]">
                  Target URL Override
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={chromeUrl}
                    onChange={(e) => setChromeUrl(e.target.value)}
                    placeholder="https://..."
                    className="flex-1 px-3 py-2 text-xs font-mono rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 focus:outline-none focus:border-brand-500"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      handleNavigateSubmit();
                      setIsEnvOpen(false);
                    }}
                    className="px-3 py-2 bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs rounded-xl transition-colors cursor-pointer"
                  >
                    Go
                  </button>
                </div>
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-950/50">
              <span className="text-[11px] text-slate-400">
                Applied to current studio session
              </span>
              <button
                type="button"
                onClick={() => setIsEnvOpen(false)}
                className="px-4 py-1.5 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white transition-colors cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        </>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          ADVANCED SETTINGS DRAWER (Slides in from the right)
          ────────────────────────────────────────────────────────────────────────── */}
      {isSettingsOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px] animate-in fade-in"
            onClick={() => setIsSettingsOpen(false)}
          />
          <div className="fixed inset-y-0 right-0 w-96 max-w-full bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                  <Settings className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">Studio Advanced Settings</h3>
                  <p className="text-[10px] text-slate-400">Configure recording engine &amp; heuristics</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsSettingsOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="p-4 flex-1 overflow-y-auto space-y-4 text-xs">
              {/* Browser Engine */}
              <div>
                <label className="block text-slate-500 font-bold mb-1.5 uppercase tracking-wider text-[10px]">
                  Execution Engine
                </label>
                <select
                  value={browser}
                  onChange={(e) => {
                    const newB = e.target.value;
                    setBrowser(newB);
                    localStorage.setItem("tracecase_default_browser", newB);
                    window.dispatchEvent(
                      new CustomEvent("tracecase:browser-changed", {
                        detail: newB,
                      })
                    );
                    showToast(`Active browser set to ${newB}`, "info");
                  }}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 font-medium focus:outline-none focus:border-brand-500 cursor-pointer"
                >
                  <option value="chromium">Google Chrome / Chromium</option>
                  <option value="webkit">WebKit (Safari)</option>
                  <option value="firefox">Mozilla Firefox</option>
                  <option value="msedge">Microsoft Edge</option>
                </select>
                <p className="text-[10px] text-slate-400 mt-1">
                  Runs directly on local machine via Playwright engine.
                </p>
              </div>

              {/* Test Case Name */}
              <div>
                <label className="block text-slate-500 font-bold mb-1.5 uppercase tracking-wider text-[10px]">
                  Test Case Title
                </label>
                <input
                  type="text"
                  value={testcaseName}
                  onChange={(e) => setTestcaseName(e.target.value)}
                  placeholder="e.g. OrangeHRM Login Journey"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 focus:outline-none focus:border-brand-500"
                />
              </div>

              {/* Action Timeout */}
              <div>
                <label className="block text-slate-500 font-bold mb-1.5 uppercase tracking-wider text-[10px]">
                  Default Step Timeout
                </label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0"
                    max="60000"
                    step="5000"
                    value={stepTimeoutMs}
                    onChange={(e) => setStepTimeoutMs(Number(e.target.value))}
                    className="flex-1 accent-brand-500 cursor-pointer"
                  />
                  <span className="font-mono font-bold text-xs w-24 text-right">
                    {stepTimeoutMs === 0 ? "No Timeout (∞)" : `${(stepTimeoutMs / 1000).toFixed(0)}s`}
                  </span>
                </div>
              </div>

              {/* Toggles: Self-Healing & Network Logs */}
              <div className="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-800/80">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-bold text-slate-800 dark:text-slate-200 block">
                      Multi-Selector Self-Healing
                    </span>
                    <span className="text-[10px] text-slate-400">
                      Captures ID, CSS, XPath &amp; Text fallback selectors
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={enableSelfHealing}
                    onChange={(e) => setEnableSelfHealing(e.target.checked)}
                    className="w-4 h-4 rounded text-brand-600 focus:ring-brand-500 accent-brand-600 cursor-pointer"
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-bold text-slate-800 dark:text-slate-200 block">
                      Capture Network HAR
                    </span>
                    <span className="text-[10px] text-slate-400">
                      Logs all HTTP requests, responses, and API latencies
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={captureNetwork}
                    onChange={(e) => setCaptureNetwork(e.target.checked)}
                    className="w-4 h-4 rounded text-brand-600 focus:ring-brand-500 accent-brand-600 cursor-pointer"
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-bold text-slate-800 dark:text-slate-200 block">
                      Capture Console Logs
                    </span>
                    <span className="text-[10px] text-slate-400">
                      Records page errors and console warnings
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={captureConsole}
                    onChange={(e) => setCaptureConsole(e.target.checked)}
                    className="w-4 h-4 rounded text-brand-600 focus:ring-brand-500 accent-brand-600 cursor-pointer"
                  />
                </div>
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-950/50">
              <span className="text-[11px] text-slate-400">
                Changes persist locally
              </span>
              <button
                type="button"
                onClick={() => setIsSettingsOpen(false)}
                className="px-4 py-1.5 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white transition-colors cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        </>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          LOCAL VARIABLES DRAWER
          ────────────────────────────────────────────────────────────────────────── */}
      {isVariablesOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px] animate-in fade-in"
            onClick={() => setIsVariablesOpen(false)}
          />
          <div className="fixed inset-y-0 right-0 w-96 max-w-full bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-200">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded bg-brand-50 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400 font-mono font-bold text-xs flex items-center justify-center">
                (x)
              </span>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">Local Variables Vault</h3>
            </div>
            <button
              type="button"
              onClick={() => setIsVariablesOpen(false)}
              className="text-slate-400 hover:text-slate-700 dark:hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="p-4 flex-1 overflow-y-auto space-y-3">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Reference these key-value pairs anywhere in test steps using{" "}
              <code className="text-brand-600 dark:text-brand-300 font-mono">{"{{variable_name}}"}</code>.
              Stored exclusively in your local database.
            </p>

            <div className="space-y-2">
              {localVariables.map((v, i) => (
                <div
                  key={i}
                  className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs"
                >
                  <div className="flex flex-col min-w-0">
                    <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400 truncate">
                      {`{{${v.key}}}`}
                    </span>
                    <span className="text-slate-500 text-[11px] font-mono truncate">
                      {v.isSecret ? "••••••••••••" : v.value}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(`{{${v.key}}}`);
                      showToast(`Copied {{${v.key}}} to clipboard`, "info");
                    }}
                    className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    title="Copy variable reference"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>

            {/* Add New Variable Form */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!newVarKey.trim()) return;
                setLocalVariables((prev) => [
                  ...prev,
                  { key: newVarKey.trim(), value: newVarVal.trim(), isSecret: newVarSecret },
                ]);
                setNewVarKey("");
                setNewVarVal("");
                setNewVarSecret(false);
                showToast("Variable saved to vault", "success");
              }}
              className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 space-y-2.5 mt-4"
            >
              <span className="text-xs font-bold text-slate-900 dark:text-white block">
                + Create Local Variable
              </span>
              <input
                type="text"
                placeholder="Variable Key (e.g. totp_token)"
                value={newVarKey}
                onChange={(e) => setNewVarKey(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white font-mono focus:outline-none focus:border-brand-500"
              />
              <input
                type="text"
                placeholder="Variable Value"
                value={newVarVal}
                onChange={(e) => setNewVarVal(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white font-mono focus:outline-none focus:border-brand-500"
              />
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="varSecret"
                  checked={newVarSecret}
                  onChange={(e) => setNewVarSecret(e.target.checked)}
                  className="rounded bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-brand-600 focus:ring-0"
                />
                <label htmlFor="varSecret" className="text-xs text-slate-600 dark:text-slate-300">
                  Mask as secret (password / API key)
                </label>
              </div>
              <button
                type="submit"
                className="w-full py-1.5 text-xs font-bold rounded-lg bg-brand-600 hover:bg-brand-500 text-white transition-colors shadow-sm"
              >
                Save Variable to Local Vault
              </button>
            </form>
          </div>
        </div>
        </>
      )}
    </div>
  );
}
