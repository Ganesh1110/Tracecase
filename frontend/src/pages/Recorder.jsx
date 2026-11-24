import React, { useEffect, useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Video,
  Globe,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowRight,
  ArrowLeft,
  RotateCcw,
  Loader2,
  StopCircle,
  Pause,
  Play,
  FolderKanban,
  Activity,
  Layers,
  Bug,
  Radio,
  Plus,
  X,
  FileUp,
  Download,
  Terminal,
  ShieldCheck,
  Maximize2,
} from "lucide-react";
import { api } from "../services/api";
import { useWebSocket } from "../context/WebSocketContext";
import { useToast } from "../context/ToastContext";
import { useProject } from "../context/ProjectContext";

export function Recorder() {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [browser, setBrowser] = useState("chromium");
  const [headless, setHeadless] = useState(true);
  const [status, setStatus] = useState({ status: "idle" });
  const [liveSteps, setLiveSteps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pauseLoading, setPauseLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Streaming Viewport State
  const [streamConnected, setStreamConnected] = useState(false);
  const [streamSessionId, setStreamSessionId] = useState(null);
  const [streamToken, setStreamToken] = useState(null);
  const [latencyMs, setLatencyMs] = useState(null);
  const [fps, setFps] = useState(0);
  const [viewportDims, setViewportDims] = useState({ width: 1280, height: 720 });

  // Browser Chrome State
  const [tabs, setTabs] = useState([{ page_id: 0, title: "Main Tab", url: "" }]);
  const [activeTabId, setActiveTabId] = useState(0);
  const [chromeUrl, setChromeUrl] = useState("");

  // JS Dialog State (alert, confirm, prompt)
  const [activeDialog, setActiveDialog] = useState(null);
  const [dialogPromptValue, setDialogPromptValue] = useState("");

  // File Upload Chooser State
  const [activeFileChooser, setActiveFileChooser] = useState(null);
  const [fileUploadPath, setFileUploadPath] = useState("");

  // Download Notification State
  const [downloadNotice, setDownloadNotice] = useState(null);

  // Diagnostics Tabs: "steps" | "network" | "console" | "errors"
  const [activeDiagTab, setActiveDiagTab] = useState("steps");
  const [consoleLogs, setConsoleLogs] = useState([]);
  const [networkRequests, setNetworkRequests] = useState([]);
  const [pageErrors, setPageErrors] = useState([]);

  // Refs
  const canvasRef = useRef(null);
  const streamWsRef = useRef(null);
  const lastMouseMoveRef = useRef(0);
  const frameCountRef = useRef(0);
  const fpsTimerRef = useRef(null);
  const timerRef = useRef(null);
  const offscreenImgRef = useRef(new Image());
  const viewportContainerRef = useRef(null);

  const { subscribe } = useWebSocket();
  const { showToast } = useToast();
  const { projects, currentProject } = useProject();
  const [selectedProjectId, setSelectedProjectId] = useState(
    currentProject?.id || "default_project"
  );
  const navigate = useNavigate();

  const isRecording = status.status === "recording";
  const isPaused = status.status === "paused";
  const isActive = isRecording || isPaused;

  useEffect(() => {
    if (currentProject?.id && !selectedProjectId) {
      setSelectedProjectId(currentProject.id);
    }
  }, [currentProject]);

  // Warn on tab close or navigate away if actively recording (BUG-012)
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isActive) {
        e.preventDefault();
        e.returnValue = "A recording is in progress. Are you sure you want to leave?";
        return e.returnValue;
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isActive]);

  const fetchStatus = async () => {
    try {
      const data = await api.getRecordingStatus();
      setStatus(data);
      if (data.steps && Array.isArray(data.steps)) {
        setLiveSteps(data.steps);
      }
      if (data.elapsed_seconds !== undefined) {
        setElapsedSeconds(data.elapsed_seconds);
      }
      if (data.url && !chromeUrl) {
        setChromeUrl(data.url);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2500);
    return () => clearInterval(interval);
  }, []);

  // Timer loop when actively recording
  useEffect(() => {
    if (status.status === "recording") {
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [status.status]);

  // Global WebSocket event subscription
  useEffect(() => {
    const unsubRecorder = subscribe("recorder", () => {
      fetchStatus();
    });
    const unsubStep = subscribe("recording_step", (event) => {
      if (event?.data?.step) {
        setLiveSteps((prev) => {
          const exists = prev.some((s) => s.number === event.data.step.number);
          if (exists) return prev;
          return [...prev, event.data.step];
        });
        if (event.data.step.console_logs) {
          setConsoleLogs((prev) => [...prev, ...event.data.step.console_logs]);
        }
        if (event.data.step.network_requests) {
          setNetworkRequests((prev) => [...prev, ...event.data.step.network_requests]);
        }
      }
      fetchStatus();
    });
    return () => {
      unsubRecorder();
      unsubStep();
    };
  }, [subscribe]);

  // FPS calculation timer
  useEffect(() => {
    if (streamConnected) {
      fpsTimerRef.current = setInterval(() => {
        setFps(frameCountRef.current);
        frameCountRef.current = 0;
      }, 1000);
    } else {
      setFps(0);
      if (fpsTimerRef.current) clearInterval(fpsTimerRef.current);
    }
    return () => {
      if (fpsTimerRef.current) clearInterval(fpsTimerRef.current);
    };
  }, [streamConnected]);

  // Latency periodic ping loop
  useEffect(() => {
    if (!streamConnected) return;
    const pingInterval = setInterval(() => {
      if (streamWsRef.current?.readyState === WebSocket.OPEN) {
        streamWsRef.current.send(
          JSON.stringify({
            type: "ping",
            data: { client_ts: performance.now() },
          })
        );
      }
    }, 2500);
    return () => clearInterval(pingInterval);
  }, [streamConnected]);

  // Connect to dedicated screencast WebSocket
  const connectStreamWebSocket = useCallback(
    (sessionId, token) => {
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
            if (payload.url) setChromeUrl(payload.url);
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
                  url: payload.url || "",
                },
              ];
            });
            setActiveTabId(payload.page_id);
            if (payload.url) setChromeUrl(payload.url);
          } else if (type === "tab_closed") {
            setTabs((prev) => prev.filter((t) => t.page_id !== payload.page_id));
          } else if (type === "tab_switched") {
            setActiveTabId(payload.page_id);
            if (payload.url) setChromeUrl(payload.url);
          } else if (type === "dialog") {
            setActiveDialog(payload);
            setDialogPromptValue(payload.default_value || "");
          } else if (type === "file_chooser") {
            setActiveFileChooser(payload);
          } else if (type === "download_started") {
            setDownloadNotice({ status: "downloading", filename: payload.filename });
          } else if (type === "download_completed") {
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
      };

      ws.onerror = (err) => {
        console.error("Stream WebSocket error:", err);
        setStreamConnected(false);
      };
    },
    []
  );

  // Clean up WebSocket on unmount
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

  // Input event dispatchers
  const sendInputEvent = (inputData) => {
    if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "input",
        data: inputData,
      })
    );
  };

  // Mouse handlers with throttling on mousemove
  const handleMouseMove = (e) => {
    const now = performance.now();
    if (now - lastMouseMoveRef.current < 25) return; // ~40 fps max
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
    const coords = getCoordinates(e);
    if (!coords) return;
    const buttonMap = { 0: "left", 1: "middle", 2: "right" };
    sendInputEvent({
      event_type: "mouse_down",
      x: coords.x,
      y: coords.y,
      button: buttonMap[e.button] || "left",
      client_viewport: coords.client_viewport,
    });
  };

  const handleMouseUp = (e) => {
    const coords = getCoordinates(e);
    if (!coords) return;
    const buttonMap = { 0: "left", 1: "middle", 2: "right" };
    sendInputEvent({
      event_type: "mouse_up",
      x: coords.x,
      y: coords.y,
      button: buttonMap[e.button] || "left",
      client_viewport: coords.client_viewport,
    });
  };

  const handleClick = (e) => {
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

  // Keyboard and Paste handlers
  const handleKeyDown = (e) => {
    if (!streamConnected) return;
    const specialKeys = [
      "Enter",
      "Escape",
      "Tab",
      "Backspace",
      "ArrowUp",
      "ArrowDown",
      "ArrowLeft",
      "ArrowRight",
    ];
    if (specialKeys.includes(e.key)) {
      e.preventDefault();
    }
    const now = performance.now();
    sendInputEvent({
      event_type: "key_down",
      key: e.key,
      code: e.code,
      client_ts: now,
    });

    // If typing printable character
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      sendInputEvent({
        event_type: "type",
        text: e.key,
      });
    }
  };

  const handleKeyUp = (e) => {
    if (!streamConnected) return;
    sendInputEvent({
      event_type: "key_up",
      key: e.key,
      code: e.code,
    });
  };

  const handlePaste = (e) => {
    if (!streamConnected) return;
    e.preventDefault();
    const text = e.clipboardData.getData("text");
    if (text) {
      sendInputEvent({
        event_type: "paste",
        text,
      });
    }
  };

  // Browser Chrome Actions
  const handleNavigateSubmit = (e) => {
    e.preventDefault();
    if (!chromeUrl.trim() || !streamWsRef.current) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "navigate",
        data: { url: chromeUrl.trim() },
      })
    );
  };

  const handleGoBack = () => {
    if (!streamWsRef.current) return;
    streamWsRef.current.send(JSON.stringify({ type: "go_back", data: {} }));
  };

  const handleGoForward = () => {
    if (!streamWsRef.current) return;
    streamWsRef.current.send(JSON.stringify({ type: "go_forward", data: {} }));
  };

  const handleReload = () => {
    if (!streamWsRef.current) return;
    streamWsRef.current.send(JSON.stringify({ type: "reload", data: {} }));
  };

  const handleSwitchTab = (pageId) => {
    setActiveTabId(pageId);
    if (!streamWsRef.current) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "switch_tab",
        data: { page_id: pageId },
      })
    );
  };

  // JS Dialog Response Handler
  const handleDialogResponse = (accept) => {
    if (!activeDialog || !streamWsRef.current) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "dialog_response",
        data: {
          dialog_id: activeDialog.dialog_id,
          accept,
          prompt_text: dialogPromptValue || undefined,
        },
      })
    );
    setActiveDialog(null);
    setDialogPromptValue("");
  };

  // File Upload Chooser Handler
  const handleFileChooserSubmit = (e) => {
    e.preventDefault();
    if (!activeFileChooser || !streamWsRef.current) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "file_upload",
        data: {
          chooser_id: activeFileChooser.chooser_id,
          files: fileUploadPath.trim() ? [fileUploadPath.trim()] : [],
        },
      })
    );
    setActiveFileChooser(null);
    setFileUploadPath("");
  };

  // Session Start / Pause / Resume / Stop
  const handleStart = async (e) => {
    e.preventDefault();
    if (!url.trim()) {
      showToast("Please enter a target URL", "error");
      return;
    }
    try {
      setLoading(true);
      setLiveSteps([]);
      setConsoleLogs([]);
      setNetworkRequests([]);
      setPageErrors([]);
      setElapsedSeconds(0);
      setTabs([{ page_id: 0, title: "Main Tab", url: url.trim() }]);
      setActiveTabId(0);
      setChromeUrl(url.trim());

      const session = await api.startRecording({
        url: url.trim(),
        name: name.trim() || undefined,
        browser,
        headless: true, // Always headless in embedded mode
        timeout: 30000,
        project_id: selectedProjectId || "default_project",
        embedded: true,
      });

      setStatus(session);
      showToast("Recording session launched!", "success");

      // Connect to embedded screencast WebSocket
      if (session.session_id) {
        connectStreamWebSocket(session.session_id, session.stream_token);
      }
    } catch (err) {
      showToast("Failed to start recorder: " + err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    try {
      setPauseLoading(true);
      const res = await api.pauseRecording();
      setStatus(res);
      showToast("Recording paused", "info");
    } catch (err) {
      showToast("Failed to pause recording: " + err.message, "error");
    } finally {
      setPauseLoading(false);
    }
  };

  const handleResume = async () => {
    try {
      setPauseLoading(true);
      const res = await api.resumeRecording();
      setStatus(res);
      showToast("Recording resumed", "success");
    } catch (err) {
      showToast("Failed to resume recording: " + err.message, "error");
    } finally {
      setPauseLoading(false);
    }
  };

  const handleStop = async () => {
    try {
      setLoading(true);
      showToast("Finalizing recording and saving test case...", "info");
      const res = await api.stopRecording();
      setStatus(res);
      if (streamWsRef.current) {
        streamWsRef.current.close();
      }
      showToast("Recording finalized and test case generated!", "success");
      if (res.testcase_id) {
        navigate(`/testcases/${res.testcase_id}`);
      }
    } catch (err) {
      showToast("Failed to stop recording: " + err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  const formatTimer = (secs) => {
    const mins = Math.floor(secs / 60);
    const remainderSecs = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remainderSecs
      .toString()
      .padStart(2, "0")}`;
  };

  return (
    <div className="space-y-5 animate-in fade-in duration-300">
      {/* Header & Status Indicator */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5">
            <Video className="w-6 h-6 text-rose-500" />
            <span>Browser Recorder Workspace</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Interact directly with the embedded browser below. Every click, type, and
            navigation is captured in real time into an executable test case.
          </p>
        </div>

        {/* Live Active Pill Indicator */}
        {isActive && (
          <div className="flex items-center gap-3 bg-white dark:bg-surface-cardDark px-4 py-2 rounded-xl border border-slate-200 dark:border-surface-borderDark shadow-sm">
            <span className="relative flex h-3 w-3">
              {isRecording && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              )}
              <span
                className={`relative inline-flex rounded-full h-3 w-3 ${
                  isRecording ? "bg-rose-500" : "bg-amber-500"
                }`}
              ></span>
            </span>
            <div className="text-xs">
              <span className="font-semibold text-slate-800 dark:text-slate-200 uppercase tracking-wider">
                {isRecording ? "Recording Live" : "Paused"}
              </span>
              <span className="text-slate-400 ml-2 font-mono">
                {formatTimer(elapsedSeconds)}
              </span>
            </div>
            {streamConnected && (
              <span className="ml-2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 flex items-center gap-1">
                <span>{fps} FPS</span>
                {latencyMs !== null && <span>• {latencyMs}ms</span>}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Main Split Layout: Left Embedded Viewport & Controls, Right Captured Timeline & Diagnostics */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* Left Column (8 cols): Embedded Browser Chrome & Live Viewport */}
        <div className="xl:col-span-8 space-y-4">
          {/* Top Session Configuration & Controls Bar */}
          <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <form onSubmit={handleStart} className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
                <div className="md:col-span-5">
                  <div className="relative">
                    <Globe className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                    <input
                      type="text"
                      placeholder="https://example.com or http://localhost:3000"
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      disabled={isActive}
                      className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                    />
                  </div>
                </div>

                <div className="md:col-span-4">
                  <input
                    type="text"
                    placeholder="Test case name (optional)"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={isActive}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  />
                </div>

                <div className="md:col-span-3 flex items-center justify-end gap-2">
                  {isActive ? (
                    <>
                      {isRecording ? (
                        <button
                          type="button"
                          onClick={handlePause}
                          disabled={pauseLoading}
                          className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-white transition-all shadow-sm"
                          title="Pause recording"
                        >
                          <Pause className="w-3.5 h-3.5" />
                          <span>Pause</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={handleResume}
                          disabled={pauseLoading}
                          className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-all shadow-sm"
                          title="Resume recording"
                        >
                          <Play className="w-3.5 h-3.5" />
                          <span>Resume</span>
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={handleStop}
                        disabled={loading}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/25 transition-all"
                        title="Stop & Save test case"
                      >
                        {loading ? (
                          <>
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            <span>Saving...</span>
                          </>
                        ) : (
                          <>
                            <StopCircle className="w-3.5 h-3.5" />
                            <span>Stop & Save</span>
                          </>
                        )}
                      </button>
                    </>
                  ) : (
                    <button
                      type="submit"
                      disabled={loading}
                      className="flex items-center justify-center gap-2 w-full px-5 py-2 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/25 transition-all disabled:opacity-50"
                    >
                      {loading ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Launching Browser...</span>
                        </>
                      ) : (
                        <>
                          <Video className="w-4 h-4" />
                          <span>Start Recording</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            </form>
          </div>

          {/* Embedded Browser Container */}
          <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-slate-900 overflow-hidden shadow-lg flex flex-col">
            {/* Browser Chrome: Tab Strip */}
            <div className="flex items-center gap-1 px-3 pt-2 bg-slate-800/90 border-b border-slate-700/80 overflow-x-auto select-none">
              {tabs.map((tab) => (
                <div
                  key={tab.page_id}
                  onClick={() => handleSwitchTab(tab.page_id)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-t-lg text-xs font-medium cursor-pointer transition-all ${
                    activeTabId === tab.page_id
                      ? "bg-slate-900 text-white border-t-2 border-brand-500"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-750"
                  }`}
                >
                  <Globe className="w-3 h-3 text-slate-400" />
                  <span className="truncate max-w-[140px]">
                    {tab.title || `Tab #${tab.page_id + 1}`}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    #{tab.page_id}
                  </span>
                </div>
              ))}
            </div>

            {/* Browser Chrome: Navigation Controls & URL Bar */}
            <div className="flex items-center gap-2 px-3 py-2 bg-slate-900 border-b border-slate-800 text-slate-300">
              <button
                type="button"
                onClick={handleGoBack}
                disabled={!isActive}
                className="p-1 rounded-lg hover:bg-slate-800 disabled:opacity-40 transition-colors"
                title="Go Back"
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={handleGoForward}
                disabled={!isActive}
                className="p-1 rounded-lg hover:bg-slate-800 disabled:opacity-40 transition-colors"
                title="Go Forward"
              >
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={handleReload}
                disabled={!isActive}
                className="p-1 rounded-lg hover:bg-slate-800 disabled:opacity-40 transition-colors"
                title="Reload"
              >
                <RotateCcw className="w-4 h-4" />
              </button>

              <form onSubmit={handleNavigateSubmit} className="flex-1 min-w-0">
                <div className="relative flex items-center">
                  <ShieldCheck className="absolute left-2.5 w-3.5 h-3.5 text-emerald-400" />
                  <input
                    type="text"
                    value={chromeUrl}
                    onChange={(e) => setChromeUrl(e.target.value)}
                    disabled={!isActive}
                    placeholder="Enter URL and press Enter..."
                    className="w-full pl-8 pr-3 py-1 text-xs font-mono rounded-lg bg-slate-950 text-slate-200 border border-slate-800 focus:outline-none focus:border-brand-500 disabled:opacity-50"
                  />
                </div>
              </form>

              <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400 shrink-0">
                <span>
                  {viewportDims.width}×{viewportDims.height}
                </span>
                <span
                  className={`w-2 h-2 rounded-full ${
                    streamConnected ? "bg-emerald-500 animate-pulse" : "bg-slate-600"
                  }`}
                  title={streamConnected ? "Live Screencast Stream Connected" : "Stream Idle"}
                ></span>
              </div>
            </div>

            {/* Viewport Canvas Area with Input Forwarding */}
            <div
              ref={viewportContainerRef}
              tabIndex={0}
              onKeyDown={handleKeyDown}
              onKeyUp={handleKeyUp}
              onPaste={handlePaste}
              className="relative w-full aspect-video bg-black flex items-center justify-center overflow-hidden outline-none cursor-crosshair select-none"
            >
              {/* Live Screencast Canvas */}
              <canvas
                ref={canvasRef}
                onMouseMove={handleMouseMove}
                onMouseDown={handleMouseDown}
                onMouseUp={handleMouseUp}
                onClick={handleClick}
                onDoubleClick={handleDoubleClick}
                onWheel={handleWheel}
                onContextMenu={handleContextMenu}
                className={`max-w-full max-h-full object-contain ${
                  isActive ? "block" : "hidden"
                }`}
              />

              {/* Inactive or Loading Placeholder */}
              {!isActive && (
                <div className="text-center p-8 space-y-3">
                  <div className="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center mx-auto text-rose-500 shadow-inner">
                    <Video className="w-6 h-6" />
                  </div>
                  <h3 className="text-sm font-semibold text-slate-200">
                    Embedded Browser Viewport
                  </h3>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto leading-relaxed">
                    Click <strong>Start Recording</strong> above to launch the headless
                    browser session. It will stream live into this canvas with zero pop-up
                    windows.
                  </p>
                </div>
              )}

              {isActive && !streamConnected && (
                <div className="absolute inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center">
                  <div className="flex items-center gap-3 text-xs text-slate-300">
                    <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
                    <span>Connecting live screencast stream...</span>
                  </div>
                </div>
              )}

              {/* JS Dialog Modal Overlay (alert, confirm, prompt) */}
              {activeDialog && (
                <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-40">
                  <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 max-w-md w-full shadow-2xl space-y-4 animate-in zoom-in-95">
                    <div className="flex items-center gap-2.5 text-amber-400">
                      <AlertCircle className="w-5 h-5 shrink-0" />
                      <h4 className="text-sm font-bold text-white capitalize">
                        JavaScript {activeDialog.dialog_type || "Dialog"}
                      </h4>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {activeDialog.message}
                    </p>
                    {activeDialog.dialog_type === "prompt" && (
                      <input
                        type="text"
                        value={dialogPromptValue}
                        onChange={(e) => setDialogPromptValue(e.target.value)}
                        placeholder="Enter value..."
                        className="w-full px-3 py-1.5 text-xs rounded-lg bg-slate-950 border border-slate-700 text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
                        autoFocus
                      />
                    )}
                    <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                      {activeDialog.dialog_type !== "alert" && (
                        <button
                          type="button"
                          onClick={() => handleDialogResponse(false)}
                          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
                        >
                          Cancel
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDialogResponse(true)}
                        className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 hover:bg-brand-500 text-white transition-colors"
                      >
                        OK
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* File Chooser Prompt Overlay */}
              {activeFileChooser && (
                <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-40">
                  <form
                    onSubmit={handleFileChooserSubmit}
                    className="bg-slate-900 border border-slate-700 rounded-2xl p-5 max-w-md w-full shadow-2xl space-y-4 animate-in zoom-in-95"
                  >
                    <div className="flex items-center gap-2.5 text-blue-400">
                      <FileUp className="w-5 h-5 shrink-0" />
                      <h4 className="text-sm font-bold text-white">
                        File Upload Request
                      </h4>
                    </div>
                    <p className="text-xs text-slate-300">
                      The application requested a file upload. Specify the path of the file
                      on disk to supply:
                    </p>
                    <input
                      type="text"
                      value={fileUploadPath}
                      onChange={(e) => setFileUploadPath(e.target.value)}
                      placeholder="/absolute/path/to/file.png"
                      className="w-full px-3 py-1.5 text-xs rounded-lg bg-slate-950 border border-slate-700 text-white focus:outline-none focus:ring-1 focus:ring-brand-500 font-mono"
                      autoFocus
                    />
                    <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                      <button
                        type="button"
                        onClick={() => setActiveFileChooser(null)}
                        className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors"
                      >
                        Upload File
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* Download Notification Banner */}
              {downloadNotice && (
                <div className="absolute bottom-3 right-3 bg-slate-900 border border-slate-700 rounded-xl px-4 py-2.5 shadow-xl flex items-center gap-3 text-xs text-slate-200 z-30 animate-in slide-in-from-bottom-2">
                  <Download className="w-4 h-4 text-emerald-400 animate-bounce" />
                  <div>
                    <span className="font-semibold block">{downloadNotice.filename}</span>
                    <span className="text-[10px] text-slate-400">
                      {downloadNotice.status === "downloading"
                        ? "Downloading..."
                        : "Download complete and saved to disk"}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column (4 cols): Live Step Timeline & Diagnostics */}
        <div className="xl:col-span-4 space-y-4">
          <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col h-[640px]">
            {/* Tab Navigation */}
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-surface-borderDark pb-2.5 mb-3">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setActiveDiagTab("steps")}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all ${
                    activeDiagTab === "steps"
                      ? "bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  Steps ({liveSteps.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveDiagTab("network")}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all ${
                    activeDiagTab === "network"
                      ? "bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  Network
                </button>
                <button
                  type="button"
                  onClick={() => setActiveDiagTab("console")}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all ${
                    activeDiagTab === "console"
                      ? "bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  Console
                </button>
                <button
                  type="button"
                  onClick={() => setActiveDiagTab("errors")}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all ${
                    activeDiagTab === "errors"
                      ? "bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  Errors
                </button>
              </div>
            </div>

            {/* Tab 1: Live Steps Timeline */}
            {activeDiagTab === "steps" && (
              <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
                {liveSteps.length === 0 ? (
                  <div className="text-center py-16 px-4 border border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
                    <Activity className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
                    <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
                      {isActive
                        ? "Interact with the embedded browser to record steps."
                        : "Start a session to stream user actions in real-time."}
                    </p>
                  </div>
                ) : (
                  liveSteps.map((step, idx) => (
                    <div
                      key={step.number || idx}
                      className="p-3 rounded-xl border border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/40 flex items-start gap-3 hover:border-slate-200 transition-all text-xs"
                    >
                      <span className="w-5 h-5 rounded-full bg-brand-500/10 text-brand-600 dark:text-brand-400 font-bold text-[10px] flex items-center justify-center shrink-0 mt-0.5">
                        {step.number || idx + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="px-1.5 py-0.2 text-[9px] font-bold rounded uppercase bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                            {step.action_type || "action"}
                          </span>
                          <span className="font-medium text-slate-900 dark:text-slate-100 truncate">
                            {step.description_short || step.action_type}
                          </span>
                        </div>
                        {(step.element?.selector || step.selector) && (
                          <p className="text-[10px] font-mono text-slate-400 truncate mt-1">
                            {step.element?.selector || step.selector}
                          </p>
                        )}
                        {step.input_value && (
                          <p className="text-[10px] text-slate-600 dark:text-slate-300 mt-0.5">
                            Value:{" "}
                            <span className="font-mono bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-200 dark:border-slate-700">
                              {step.input_value}
                            </span>
                          </p>
                        )}
                      </div>
                      {step.screenshot_path && (
                        <div className="shrink-0 w-10 h-7 rounded border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-100 dark:bg-slate-800">
                          <img
                            src={`/api/testcases/screenshot?path=${encodeURIComponent(
                              step.screenshot_path
                            )}`}
                            alt="thumb"
                            className="w-full h-full object-cover"
                            onError={(e) => (e.target.style.display = "none")}
                          />
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab 2: Network Inspector */}
            {activeDiagTab === "network" && (
              <div className="flex-1 overflow-y-auto space-y-2 pr-1 font-mono text-[11px]">
                {networkRequests.length === 0 ? (
                  <div className="text-center py-16 text-slate-400 text-xs italic">
                    No network requests captured for this session yet.
                  </div>
                ) : (
                  networkRequests.map((req, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 flex items-center justify-between gap-2"
                    >
                      <div className="flex items-center gap-2 truncate">
                        <span className="font-bold text-[10px] uppercase text-brand-500">
                          {req.method}
                        </span>
                        <span className="truncate text-slate-700 dark:text-slate-300">
                          {req.url}
                        </span>
                      </div>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          req.status >= 400
                            ? "bg-rose-50 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400"
                            : "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400"
                        }`}
                      >
                        {req.status || "---"}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab 3: Console Logs */}
            {activeDiagTab === "console" && (
              <div className="flex-1 overflow-y-auto space-y-1.5 pr-1 font-mono text-[11px]">
                {consoleLogs.length === 0 ? (
                  <div className="text-center py-16 text-slate-400 text-xs italic">
                    No console output captured yet.
                  </div>
                ) : (
                  consoleLogs.map((log, idx) => (
                    <div
                      key={idx}
                      className={`p-2 rounded-lg border text-xs leading-relaxed ${
                        log.level === "error"
                          ? "bg-rose-50/50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-900/50 text-rose-600 dark:text-rose-400"
                          : log.level === "warn"
                          ? "bg-amber-50/50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900/50 text-amber-600 dark:text-amber-400"
                          : "bg-slate-50 dark:bg-slate-900/40 border-slate-100 dark:border-slate-800 text-slate-700 dark:text-slate-300"
                      }`}
                    >
                      <span className="font-bold uppercase text-[9px] mr-1.5 opacity-75">
                        [{log.level}]
                      </span>
                      <span>{log.message}</span>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab 4: Page Errors */}
            {activeDiagTab === "errors" && (
              <div className="flex-1 overflow-y-auto space-y-2 pr-1 font-mono text-xs">
                {pageErrors.length === 0 ? (
                  <div className="text-center py-16 text-slate-400 text-xs italic">
                    Zero uncaught page errors detected.
                  </div>
                ) : (
                  pageErrors.map((err, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-600 dark:text-rose-400 space-y-1"
                    >
                      <span className="font-bold block text-[11px]">Uncaught Error:</span>
                      <p className="leading-relaxed">{err.message}</p>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Bottom Target Link if Completed */}
            {status.status === "completed" && status.testcase_id && (
              <button
                type="button"
                onClick={() => navigate(`/testcases/${status.testcase_id}`)}
                className="mt-3 flex items-center justify-center gap-2 w-full py-2.5 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 transition-all"
              >
                <span>View Recorded Test Case</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
