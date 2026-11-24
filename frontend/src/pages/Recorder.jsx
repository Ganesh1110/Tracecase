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
  const [browser, setBrowser] = useState("chromium");
  const [headless, setHeadless] = useState(true);
  const [status, setStatus] = useState({ status: "idle" });

  // Clean empty step list by default (matching Screenshot 1)
  const [liveSteps, setLiveSteps] = useState([]);

  const [loading, setLoading] = useState(false);
  const [pauseLoading, setPauseLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(160); // 02:40 timer

  // Authoring & Interaction States
  const [manualInteraction, setManualInteraction] = useState(true);
  const [nlPrompt, setNlPrompt] = useState("");
  const [promptLoading, setPromptLoading] = useState(false);
  const [isVariablesOpen, setIsVariablesOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isEnvOpen, setIsEnvOpen] = useState(false);
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
      if (data.session_id && data.status === "recording" && !streamConnected) {
        setStreamSessionId(data.session_id);
        connectStreamWebSocket(data.session_id, data.stream_token);
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
      setStatus((prev) => ({ ...prev, status: "error", error: payload?.error }));
      showToast("Recording error: " + (payload?.error || "Unknown error"), "error");
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
                url: payload.url || "about:blank",
              },
            ];
          });
          setActiveTabId(payload.page_id);
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
    };

    ws.onerror = (err) => {
      console.error("Stream WebSocket error:", err);
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
    if (now - lastMouseMoveRef.current < 25) return;
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

  const handleKeyDown = (e) => {
    if (!streamConnected || !manualInteraction) return;
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

    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      sendInputEvent({
        event_type: "type",
        text: e.key,
      });
    }
  };

  const handleKeyUp = (e) => {
    if (!streamConnected || !manualInteraction) return;
    sendInputEvent({
      event_type: "key_up",
      key: e.key,
      code: e.code,
    });
  };

  const handlePaste = (e) => {
    if (!streamConnected || !manualInteraction) return;
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
    if (!chromeUrl.trim()) return;
    const targetUrl = chromeUrl.startsWith("http") ? chromeUrl.trim() : `https://${chromeUrl.trim()}`;
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

  const handleResetSession = () => {
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
    const finalUrl = (targetUrl && targetUrl.trim()) || "https://www.google.com";

    try {
      setLoading(true);
      setElapsedSeconds(0);
      setTabs([{ page_id: 0, title: "Google", url: finalUrl }]);
      setActiveTabId(0);
      setChromeUrl(finalUrl);

      const session = await api.startRecording({
        url: finalUrl,
        name: testcaseName.trim() || undefined,
        browser,
        headless: true,
        timeout: 30000,
        project_id: selectedProjectId || "default_project",
        embedded: true,
      });

      setStatus(session);
      showToast("Local Browser Studio session launched!", "success");

      if (session.session_id) {
        connectStreamWebSocket(session.session_id, session.stream_token);
      }
    } catch (err) {
      showToast("Failed to start studio: " + err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    try {
      setPauseLoading(true);
      const res = await api.pauseRecording();
      setStatus(res);
      showToast("Session paused", "info");
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
      showToast("Session resumed", "success");
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
    const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(query)}`;

    // Add recorded steps sequentially
    setLiveSteps((prev) => [
      ...prev,
      {
        number: prev.length + 1,
        action: "navigate",
        action_type: "navigate",
        description: `Open 'https://www.google.com'`,
        url: "https://www.google.com",
        selector: "window.location",
      },
      {
        number: prev.length + 2,
        action: "click",
        action_type: "click",
        description: `Click on the search input field`,
        selector: 'input[name="q"], textarea[name="q"]',
      },
      {
        number: prev.length + 3,
        action: "type",
        action_type: "type",
        description: `Type in search input field '${query}'`,
        input_value: query,
        selector: 'input[name="q"], textarea[name="q"]',
      },
      {
        number: prev.length + 4,
        action: "click",
        action_type: "click",
        description: `Click on the 'Google Search' button`,
        selector: 'input[name="btnK"]',
      },
    ]);

    setPassedCount((prev) => prev + 4);
    setChromeUrl(searchUrl);
    setTabs([{ page_id: 0, title: `${query} - Google Search`, url: searchUrl }]);
    setGoogleQuery("");

    // Forward to live browser session if connected
    sendInputEvent({
      event_type: "navigate",
      url: searchUrl,
    });

    showToast(`Executed search: "${query}"`, "success");
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
      <header className="h-14 px-4 bg-white dark:bg-surface-panelDark border-b border-slate-200 dark:border-surface-borderDark flex items-center justify-between shrink-0 z-30 transition-colors">
        {/* Left: Authoring Steps, Timer, Passed/Edited/Warning Counters, Pause */}
        <div className="flex items-center gap-3">
          {/* Brand & Authoring Steps */}
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center text-white shadow-sm shrink-0">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-900 dark:text-white">
                Authoring Steps
              </span>
              {/* Timer Pill */}
              <span className="px-2.5 py-0.5 rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-[11px] font-mono font-medium text-slate-700 dark:text-slate-300">
                {formatTimer(elapsedSeconds)}
              </span>
            </div>
          </div>

          <div className="h-4 w-px bg-slate-200 dark:bg-slate-700 mx-1" />

          {/* Counter Dots (Passed, Additions/Edits, Warnings) */}
          <div className="flex items-center gap-3 text-xs font-semibold">
            {/* Green: Passed / Total steps */}
            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{passedCount}</span>
            </span>
            {/* Purple: Edits / Dynamic inputs */}
            <span className="flex items-center gap-1 text-indigo-600 dark:text-indigo-400">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
              <span>{editedCount}</span>
            </span>
            {/* Yellow: Warnings / Alerts */}
            <span className="flex items-center gap-1 text-amber-500">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{warnCount}</span>
            </span>
          </div>

          <div className="h-4 w-px bg-slate-200 dark:bg-slate-700 mx-1" />

          {/* Replay Button */}
          <button
            type="button"
            onClick={handleRefreshPage}
            className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-800 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            title="Refresh / Replay"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          {/* Pause / Resume Button */}
          <button
            type="button"
            onClick={isRecording ? handlePause : handleResume}
            disabled={pauseLoading}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
              isRecording
                ? "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700 hover:bg-amber-100"
                : "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-700 hover:bg-emerald-100"
            }`}
          >
            {isRecording ? (
              <>
                <Pause className="w-3 h-3 fill-current" />
                <span>Pause</span>
              </>
            ) : (
              <>
                <Play className="w-3 h-3 fill-current" />
                <span>Resume</span>
              </>
            )}
          </button>
        </div>

        {/* Right: Environment, Advanced Settings, Variables, Save, Exit */}
        <div className="flex items-center gap-2">
          {/* Set Environment */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsEnvOpen(!isEnvOpen)}
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <Monitor className="w-3.5 h-3.5 text-slate-500" />
              <span>Set Environment</span>
            </button>
            {isEnvOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-xl p-3 z-50 text-xs space-y-2">
                <span className="font-bold text-slate-700 dark:text-slate-200 block">
                  Environment Resolution
                </span>
                <button
                  onClick={() => {
                    setViewportDims({ width: 1440, height: 900 });
                    setIsEnvOpen(false);
                  }}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 flex items-center justify-between"
                >
                  <span>Desktop (1440 &times; 900)</span>
                  {viewportDims.width === 1440 && <Check className="w-3.5 h-3.5 text-brand-500" />}
                </button>
                <button
                  onClick={() => {
                    setViewportDims({ width: 1280, height: 720 });
                    setIsEnvOpen(false);
                  }}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 flex items-center justify-between"
                >
                  <span>Laptop (1280 &times; 720)</span>
                  {viewportDims.width === 1280 && <Check className="w-3.5 h-3.5 text-brand-500" />}
                </button>
                <button
                  onClick={() => {
                    setViewportDims({ width: 390, height: 844 });
                    setIsEnvOpen(false);
                  }}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 flex items-center justify-between"
                >
                  <span>Mobile View (390 &times; 844)</span>
                  {viewportDims.width === 390 && <Check className="w-3.5 h-3.5 text-brand-500" />}
                </button>
              </div>
            )}
          </div>

          {/* Advanced Settings */}
          <button
            type="button"
            onClick={() => setIsSettingsOpen(!isSettingsOpen)}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <Settings className="w-3.5 h-3.5 text-slate-500" />
            <span>Advanced Settings</span>
            <span className="px-1 text-[10px] font-bold rounded bg-slate-200 dark:bg-slate-700">1</span>
          </button>

          {/* Variables (x) */}
          <button
            type="button"
            onClick={() => setIsVariablesOpen(!isVariablesOpen)}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <span className="font-mono font-bold text-[11px]">(x)</span>
            <span className="hidden sm:inline">Variables</span>
          </button>

          {/* Save Button (Green, Opens Save Modal) */}
          <button
            type="button"
            onClick={() => setIsSaveModalOpen(true)}
            className="px-4 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm shadow-emerald-600/20 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Save className="w-3.5 h-3.5" />
            <span>Save</span>
          </button>

          {/* Exit Button */}
          <button
            type="button"
            onClick={() => navigate("/testcases")}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
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
                Google Chrome
              </span>
              {/* Pink Recording steps Pill */}
              <span className="px-2 py-0.5 rounded-full bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-[10px] font-semibold text-rose-600 dark:text-rose-400 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                <span>Recording steps</span>
              </span>
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
                  onClick={() => setDeviceMode("desktop")}
                  className={`px-2 py-1 rounded text-xs flex items-center gap-1 transition-colors ${
                    deviceMode === "desktop"
                      ? "bg-white dark:bg-slate-700 text-brand-600 dark:text-brand-400 font-bold shadow-xs"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-300"
                  }`}
                  title="Desktop Viewport (1440x900)"
                >
                  <Monitor className="w-3 h-3" />
                  <span className="text-[10px]">Desktop</span>
                </button>
                <button
                  type="button"
                  onClick={() => setDeviceMode("mobile")}
                  className={`px-2 py-1 rounded text-xs flex items-center gap-1 transition-colors ${
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
            tabIndex={0}
            onKeyDown={handleKeyDown}
            onKeyUp={handleKeyUp}
            onPaste={handlePaste}
            className={`flex-1 relative bg-slate-100 dark:bg-slate-950 flex flex-col items-center justify-center overflow-auto outline-none select-none cursor-default ${
              deviceMode === "mobile" ? "p-4" : ""
            }`}
          >
            <div
              className={`flex flex-col items-center justify-center transition-all ${
                deviceMode === "mobile"
                  ? "w-[393px] h-[780px] bg-white dark:bg-slate-900 rounded-[40px] border-4 border-slate-700 shadow-2xl relative overflow-hidden shrink-0"
                  : "w-full h-full relative"
              }`}
            >
              {deviceMode === "mobile" && (
                <div className="absolute top-2 left-1/2 -translate-x-1/2 w-28 h-4 bg-slate-800 rounded-full z-30" />
              )}
              {/* Live Screencast Canvas (Active Stream) */}
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
                  streamConnected ? "block" : "hidden"
                }`}
              />

              {/* Default Google Homepage View */}
              {!streamConnected && (
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
          ADVANCED SETTINGS MODAL
          ────────────────────────────────────────────────────────────────────────── */}
      {isSettingsOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-sm w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Settings className="w-4 h-4 text-brand-500" />
                <span>Advanced Settings</span>
              </h3>
              <button onClick={() => setIsSettingsOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-500 font-bold mb-1">Browser Engine</label>
                <select
                  value={browser}
                  onChange={(e) => setBrowser(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-white"
                >
                  <option value="chromium">Chromium</option>
                  <option value="firefox">Firefox</option>
                  <option value="webkit">WebKit (Safari)</option>
                </select>
              </div>
              <div>
                <label className="block text-slate-500 font-bold mb-1">Test Case Name</label>
                <input
                  type="text"
                  value={testcaseName}
                  onChange={(e) => setTestcaseName(e.target.value)}
                  className="w-full px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-white"
                />
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setIsSettingsOpen(false)}
                className="px-4 py-1.5 text-xs font-bold rounded-lg bg-brand-600 text-white hover:bg-brand-500"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          LOCAL VARIABLES DRAWER
          ────────────────────────────────────────────────────────────────────────── */}
      {isVariablesOpen && (
        <div className="fixed inset-y-0 right-0 w-96 bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-200">
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
      )}
    </div>
  );
}
