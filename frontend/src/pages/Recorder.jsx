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
} from "lucide-react";
import { api } from "../services/api";
import { useWebSocket } from "../context/WebSocketContext";
import { useToast } from "../context/ToastContext";
import { useProject } from "../context/ProjectContext";

export function Recorder() {
  const [url, setUrl] = useState("");
  const [testcaseName, setTestcaseName] = useState("New Test Case");
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [browser, setBrowser] = useState("chromium");
  const [headless, setHeadless] = useState(true);
  const [status, setStatus] = useState({ status: "idle" });

  // Clean empty step list by default
  const [liveSteps, setLiveSteps] = useState([]);

  const [loading, setLoading] = useState(false);
  const [pauseLoading, setPauseLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Authoring & Interaction States
  const [manualInteraction, setManualInteraction] = useState(true);
  const [nlPrompt, setNlPrompt] = useState("");
  const [promptLoading, setPromptLoading] = useState(false);
  const [isVariablesOpen, setIsVariablesOpen] = useState(false);
  const [activeBottomTab, setActiveBottomTab] = useState("network"); // 'network' | 'console' | 'telemetry'
  const [isDrawerCollapsed, setIsDrawerCollapsed] = useState(false);

  // Edit / Stats Counters
  const [additionsCount, setAdditionsCount] = useState(0);
  const [editedCount, setEditedCount] = useState(0);
  const [deletedCount, setDeletedCount] = useState(0);

  // Inline Step Editing State
  const [editingIndex, setEditingIndex] = useState(null);
  const [editDesc, setEditDesc] = useState("");
  const [editSelector, setEditSelector] = useState("");
  const [editValue, setEditValue] = useState("");

  // Step expansion state (expanded details)
  const [expandedSteps, setExpandedSteps] = useState({});

  // Local Variables Store
  const [localVariables, setLocalVariables] = useState([
    { key: "base_url", value: "https://example.com", isSecret: false },
    { key: "username", value: "tester@tracecase.local", isSecret: false },
    { key: "password", value: "Test@124", isSecret: true },
    { key: "totp_seed", value: "JBSWY3DPEHPK3PXP", isSecret: true },
  ]);
  const [newVarKey, setNewVarKey] = useState("");
  const [newVarVal, setNewVarVal] = useState("");
  const [newVarSecret, setNewVarSecret] = useState(false);

  // New step / condition modal
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
  const [chromeUrl, setChromeUrl] = useState("");
  const [tabs, setTabs] = useState([
    { page_id: 0, title: "New Tab", url: "about:blank" },
  ]);
  const [activeTabId, setActiveTabId] = useState(0);
  const [latencyMs, setLatencyMs] = useState(0);

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
  const frameCountRef = useRef(142);
  const viewportContainerRef = useRef(null);
  const timerRef = useRef(null);

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
        setAdditionsCount((prev) => prev + 1);
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
    sendInputEvent({
      event_type: "navigate",
      url: chromeUrl.trim(),
    });
    setLiveSteps((prev) => [
      ...prev,
      {
        number: prev.length + 1,
        action: "navigate",
        action_type: "navigate",
        description: `Go to ${chromeUrl.trim()}`,
        url: chromeUrl.trim(),
      },
    ]);
    setAdditionsCount((prev) => prev + 1);
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
        data: { url: "about:blank" },
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

  const handleDialogResponse = (accepted) => {
    if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "handle_dialog",
        data: {
          accept: accepted,
          prompt_text: accepted ? dialogPromptValue : undefined,
        },
      })
    );
    setActiveDialog(null);
  };

  const handleFileChooserSubmit = (e) => {
    e.preventDefault();
    if (!streamWsRef.current || streamWsRef.current.readyState !== WebSocket.OPEN) return;
    if (!fileUploadPath.trim()) return;
    streamWsRef.current.send(
      JSON.stringify({
        type: "handle_file_chooser",
        data: {
          files: [fileUploadPath.trim()],
        },
      })
    );
    setActiveFileChooser(null);
    setFileUploadPath("");
  };

  // Launch Session Lifecycle
  const handleStart = async (e) => {
    if (e) e.preventDefault();
    if (!url.trim()) {
      showToast("Please provide a valid starting URL", "error");
      return;
    }

    try {
      setLoading(true);
      setElapsedSeconds(0);
      setTabs([{ page_id: 0, title: "Main Tab", url: url.trim() }]);
      setActiveTabId(0);
      setChromeUrl(url.trim());

      const session = await api.startRecording({
        url: url.trim(),
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

  const handleStop = async () => {
    try {
      setLoading(true);
      showToast("Finalizing session & compiling test case locally...", "info");
      const res = await api.stopRecording();
      setStatus(res);
      if (streamWsRef.current) {
        streamWsRef.current.close();
      }
      showToast("Test case compiled and saved to local SQLite!", "success");
      if (res.testcase_id) {
        navigate(`/testcases/${res.testcase_id}`);
      }
    } catch (err) {
      showToast("Failed to stop session: " + err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  // Natural Language Prompt Authoring Dispatcher
  const handleNlPromptSubmit = (e) => {
    e.preventDefault();
    if (!nlPrompt.trim()) return;

    setPromptLoading(true);
    const raw = nlPrompt.trim();

    // Parse simple NL intentions locally
    let generatedStep = null;
    if (raw.toLowerCase().startsWith("go to ") || raw.toLowerCase().startsWith("open ")) {
      const targetUrl = raw.replace(/^(go to|open)\s+/i, "");
      generatedStep = {
        number: liveSteps.length + 1,
        action: "navigate",
        action_type: "navigate",
        description: `Go to ${targetUrl}`,
        url: targetUrl.startsWith("http") ? targetUrl : `https://${targetUrl}`,
      };
      setChromeUrl(generatedStep.url);
      sendInputEvent({ event_type: "navigate", url: generatedStep.url });
    } else if (raw.toLowerCase().startsWith("click ")) {
      const elem = raw.replace(/^click\s+(on\s+)?/i, "");
      generatedStep = {
        number: liveSteps.length + 1,
        action: "click",
        action_type: "click",
        description: `Click on ${elem}`,
        target: elem,
        selector: `text=${elem}`,
      };
    } else if (raw.toLowerCase().startsWith("type ") || raw.toLowerCase().startsWith("enter ")) {
      const val = raw.replace(/^(type|enter)\s+/i, "");
      generatedStep = {
        number: liveSteps.length + 1,
        action: "type",
        action_type: "type",
        description: `Enter text '${val}'`,
        input_value: val,
      };
    } else if (raw.toLowerCase().startsWith("if ") || raw.toLowerCase().startsWith("check ")) {
      const cond = raw.replace(/^(if|check\s+if)\s+/i, "");
      generatedStep = {
        number: liveSteps.length + 1,
        is_condition: true,
        condition_expr: cond.includes("==") ? cond : `${cond} == true`,
        then_steps: [
          {
            number: 1,
            action: "click",
            action_type: "click",
            description: `Click on confirmed target`,
          },
        ],
        else_steps: [
          {
            number: 1,
            action: "assert",
            action_type: "assert",
            description: `Assert fallback notification visible`,
          },
        ],
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
    setAdditionsCount((prev) => prev + 1);
    setNlPrompt("");
    setPromptLoading(false);
    showToast("AI Step authored locally!", "success");
  };

  // Add custom manual step
  const handleAddManualStep = () => {
    if (!newStepDesc.trim() && !newStepTarget.trim()) return;

    const step = {
      number: liveSteps.length + 1,
      action: newStepType,
      action_type: newStepType,
      description: newStepDesc || `${newStepType} on ${newStepTarget}`,
      selector: newStepTarget,
      input_value: newStepValue,
    };

    setLiveSteps((prev) => [...prev, step]);
    setAdditionsCount((prev) => prev + 1);
    setIsAddingStep(false);
    setNewStepTarget("");
    setNewStepValue("");
    setNewStepDesc("");
    showToast("Step added", "success");
  };

  // Add condition block
  const handleAddConditionBlock = () => {
    const block = {
      number: liveSteps.length + 1,
      is_condition: true,
      condition_expr: "login_button_visibility == true",
      then_steps: [
        {
          number: 1,
          action: "click",
          action_type: "click",
          description: "Click on login button",
          selector: 'a[href*="/login"]',
        },
        {
          number: 2,
          action: "click",
          action_type: "click",
          description: "Click on continue",
          selector: 'button[type="submit"]',
        },
        {
          number: 3,
          action: "type",
          action_type: "type",
          description: "Enter password {{password}}",
          input_value: "{{password}}",
          selector: 'input[type="password"]',
        },
      ],
      else_steps: [
        {
          number: 1,
          action: "click",
          action_type: "click",
          description: "Click on guest register link",
          selector: 'a[href*="/register"]',
        },
      ],
    };
    setLiveSteps((prev) => [...prev, block]);
    setAdditionsCount((prev) => prev + 1);
    showToast("Condition block created", "success");
  };

  const handleDeleteStep = (index) => {
    setLiveSteps((prev) => prev.filter((_, i) => i !== index));
    setDeletedCount((prev) => prev + 1);
    showToast("Step removed", "info");
  };

  // Inline Step Editing
  const startEditStep = (idx, step) => {
    setEditingIndex(idx);
    setEditDesc(step.description || "");
    setEditSelector(step.selector || step.target || "");
    setEditValue(step.input_value || "");
  };

  const saveEditStep = (idx) => {
    setLiveSteps((prev) =>
      prev.map((step, i) => {
        if (i !== idx) return step;
        return {
          ...step,
          description: editDesc,
          selector: editSelector,
          target: editSelector,
          input_value: editValue,
        };
      })
    );
    setEditingIndex(null);
    setEditedCount((prev) => prev + 1);
    showToast("Step updated successfully", "success");
  };

  const handleAddVariable = (e) => {
    e.preventDefault();
    if (!newVarKey.trim()) return;
    setLocalVariables((prev) => [
      ...prev,
      {
        key: newVarKey.trim(),
        value: newVarVal.trim(),
        isSecret: newVarSecret,
      },
    ]);
    setNewVarKey("");
    setNewVarVal("");
    setNewVarSecret(false);
    showToast("Variable stored in local vault", "success");
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
          TRACECASE STUDIO TOP BAR (Adaptive Theme, Stats & Actions)
          ────────────────────────────────────────────────────────────────────────── */}
      <header className="h-14 px-4 bg-white dark:bg-surface-panelDark border-b border-slate-200 dark:border-surface-borderDark flex items-center justify-between shrink-0 z-30 transition-colors">
        {/* Left: Brand / Session Breadcrumb */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center text-white shadow-md shadow-brand-500/20 shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                {isEditingTitle ? (
                  <div className="flex items-center gap-1">
                    <input
                      type="text"
                      value={testcaseName}
                      onChange={(e) => setTestcaseName(e.target.value)}
                      className="px-1.5 py-0.5 text-xs font-bold rounded bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none"
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => setIsEditingTitle(false)}
                      className="p-1 text-emerald-600 hover:text-emerald-500"
                    >
                      <Check className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <span
                    onClick={() => setIsEditingTitle(true)}
                    className="text-xs font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-1.5 cursor-pointer hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                    title="Click to rename test case"
                  >
                    {testcaseName}
                    <Edit2 className="w-2.5 h-2.5 text-slate-400 opacity-60" />
                  </span>
                )}
                <span className="px-1.5 py-0.5 text-[9px] font-bold rounded bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                  Local Studio
                </span>
              </div>
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono flex items-center gap-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    isRecording
                      ? "bg-rose-500 animate-pulse"
                      : status.status === "paused"
                      ? "bg-amber-500"
                      : "bg-slate-400"
                  }`}
                />
                {isActive ? (isRecording ? "Live Session" : "Paused") : "Draft"}
                {isActive && ` • ${formatTimer(elapsedSeconds)}`}
              </span>
            </div>
          </div>

          <div className="h-5 w-px bg-slate-200 dark:bg-slate-800 mx-1 hidden sm:block" />

          {/* Edit Stats Tracker */}
          <div className="hidden lg:flex items-center gap-1.5 text-xs font-medium">
            <span className="px-2 py-0.5 rounded-md bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border border-emerald-200/80 dark:border-emerald-800/80 font-semibold text-[11px]">
              + Additions {additionsCount}
            </span>
            <span className="px-2 py-0.5 rounded-md bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-400 border border-sky-200/80 dark:border-sky-800/80 font-semibold text-[11px]">
              ✎ Edited {editedCount}
            </span>
            <span className="px-2 py-0.5 rounded-md bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 border border-rose-200/80 dark:border-rose-800/80 font-semibold text-[11px]">
              🗑 Deleted {deletedCount}
            </span>
            <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 font-semibold text-[11px]">
              ⚙ Applied settings 03
            </span>
          </div>
        </div>

        {/* Center / Action Toolbar */}
        <div className="flex items-center gap-2">
          {/* Variables Drawer Button */}
          <button
            type="button"
            onClick={() => setIsVariablesOpen(!isVariablesOpen)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              isVariablesOpen
                ? "bg-brand-50 dark:bg-brand-950 border-brand-500 text-brand-700 dark:text-brand-300 shadow-sm"
                : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-750"
            }`}
            title="Manage Local Variables & Secrets"
          >
            <span className="font-mono font-bold text-[11px]">(x)</span>
            <span>Variables</span>
            <span className="px-1.5 py-0.2 text-[10px] rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-bold">
              {localVariables.length}
            </span>
          </button>

          {/* Replay Button */}
          <button
            type="button"
            onClick={handleRefreshPage}
            className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors shadow-sm"
            title="Replay / refresh browser page"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          {/* Pause / Resume Controls */}
          {isActive && (
            <>
              {isRecording ? (
                <button
                  type="button"
                  onClick={handlePause}
                  disabled={pauseLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-700 hover:bg-amber-100 dark:hover:bg-amber-900/40 transition-all"
                >
                  <Pause className="w-3.5 h-3.5" />
                  <span>Pause</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleResume}
                  disabled={pauseLoading}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-500 transition-all shadow-sm shadow-emerald-600/20"
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>Resume</span>
                </button>
              )}
            </>
          )}

          {/* Stop / Finalize Button or Launch Studio */}
          {isActive ? (
            <button
              type="button"
              onClick={handleStop}
              disabled={loading}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-sm shadow-rose-600/25 transition-all"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              <span>Finalize & Save</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStart}
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-sm shadow-brand-600/25 transition-all"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5 fill-current" />
              )}
              <span>Launch Studio</span>
            </button>
          )}
        </div>

        {/* Right: Manual Interaction Toggle & Zero-Leak Local Pill */}
        <div className="flex items-center gap-3">
          {/* Manual Interaction Switch */}
          <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800/80 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700/60 shadow-sm">
            <Hand
              className={`w-3.5 h-3.5 ${
                manualInteraction ? "text-brand-600 dark:text-brand-400" : "text-slate-400"
              }`}
            />
            <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">
              Manual Interaction
            </span>
            <button
              type="button"
              onClick={() => setManualInteraction(!manualInteraction)}
              className={`w-8 h-4 flex items-center rounded-full p-0.5 transition-colors cursor-pointer ${
                manualInteraction ? "bg-brand-600 justify-end" : "bg-slate-300 dark:bg-slate-600 justify-start"
              }`}
              title="Toggle direct input forwarding vs visual inspection"
            >
              <div className="w-3 h-3 rounded-full bg-white shadow-sm" />
            </button>
          </div>

          {/* Local Engine Security Pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-300 text-[11px] font-medium font-mono">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            <span>100% Local Engine</span>
            <span className="text-[10px] opacity-75">
              ({latencyMs > 0 ? `${latencyMs}ms` : "0ms"})
            </span>
          </div>
        </div>
      </header>

      {/* ──────────────────────────────────────────────────────────────────────────
          MAIN STUDIO SPLIT VIEW: LEFT (AUTHORING) + RIGHT (EMBEDDED BROWSER)
          ────────────────────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── LEFT PANE: NATURAL LANGUAGE & STEP BUILDER (~42% width) ── */}
        <div className="w-[420px] lg:w-[460px] xl:w-[480px] border-r border-slate-200 dark:border-surface-borderDark flex flex-col bg-slate-50/70 dark:bg-surface-panelDark shrink-0 transition-colors">
          {/* 1. "What do you want to test today?" Prompt Box */}
          <div className="p-3.5 border-b border-slate-200 dark:border-surface-borderDark bg-white dark:bg-slate-900/60 space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-brand-500 dark:text-brand-400" />
                What do you want to test today?
              </label>
              <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                Natural Language &rarr; Local Action
              </span>
            </div>

            <form onSubmit={handleNlPromptSubmit} className="relative">
              <input
                type="text"
                value={nlPrompt}
                onChange={(e) => setNlPrompt(e.target.value)}
                placeholder="e.g. Go to https://example.com, click login button..."
                className="w-full pl-3 pr-24 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-all font-sans"
              />
              <button
                type="submit"
                disabled={promptLoading || !nlPrompt.trim()}
                className="absolute right-1 top-1 bottom-1 px-3 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-[11px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 shadow-sm"
              >
                {promptLoading ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Sparkles className="w-3 h-3" />
                )}
                <span>Author</span>
              </button>
            </form>

            {/* Quick Action Shortcut Pills */}
            <div className="flex items-center gap-1.5 pt-0.5 overflow-x-auto text-[10px] text-slate-600 dark:text-slate-400 scrollbar-none">
              <button
                type="button"
                onClick={() => setNlPrompt("Go to https://")}
                className="px-2 py-0.5 rounded-md bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 transition-colors shrink-0"
              >
                + Navigate
              </button>
              <button
                type="button"
                onClick={() => setNlPrompt("Click on ")}
                className="px-2 py-0.5 rounded-md bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 transition-colors shrink-0"
              >
                + Click
              </button>
              <button
                type="button"
                onClick={() => setNlPrompt("Enter password {{password}}")}
                className="px-2 py-0.5 rounded-md bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 transition-colors shrink-0"
              >
                + Secret Input
              </button>
              <button
                type="button"
                onClick={handleAddConditionBlock}
                className="px-2 py-0.5 rounded-md bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 transition-colors shrink-0 font-semibold"
              >
                + If Condition
              </button>
            </div>
          </div>

          {/* 2. Step Hierarchy & Conditional Tree */}
          <div className="flex-1 overflow-y-auto p-3.5 space-y-2.5">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1">
              <span className="flex items-center gap-1.5">
                <span>Steps Sequence</span>
                <span className="px-1.5 py-0.2 rounded-full bg-slate-200 dark:bg-slate-800 text-[10px] font-bold text-slate-700 dark:text-slate-300">
                  {liveSteps.length}
                </span>
              </span>
              <button
                type="button"
                onClick={() => setIsAddingStep(true)}
                className="text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 text-[11px] font-bold flex items-center gap-1 transition-colors"
              >
                <Plus className="w-3 h-3" /> Add Step
              </button>
            </div>

            {/* Empty State */}
            {liveSteps.length === 0 && (
              <div className="py-12 text-center border border-dashed border-slate-200 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950/40 p-6 space-y-3">
                <div className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto">
                  <Activity className="w-5 h-5 text-brand-500" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-slate-800 dark:text-slate-200">
                    No steps recorded yet
                  </h4>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 max-w-xs mx-auto mt-1 leading-relaxed">
                    Interact directly with the browser canvas on the right, or type a
                    natural language prompt above to generate steps locally.
                  </p>
                </div>
              </div>
            )}

            {/* Render Steps & Branching Condition Blocks */}
            {liveSteps.map((step, idx) => {
              if (step.is_condition) {
                const isCollapsed = collapsedConditions[idx];
                const isElseExpanded = showElseSteps[idx];

                return (
                  <div
                    key={idx}
                    className="rounded-2xl border-2 border-indigo-400/50 dark:border-indigo-500/40 bg-indigo-50/20 dark:bg-indigo-950/20 p-3 space-y-3 transition-all shadow-sm"
                  >
                    {/* Condition Header Bar */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="w-5 h-5 rounded-md bg-indigo-100 dark:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 font-mono text-[11px] font-bold flex items-center justify-center shrink-0">
                          {idx + 1}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            setCollapsedConditions((prev) => ({
                              ...prev,
                              [idx]: !prev[idx],
                            }))
                          }
                          className="p-0.5 text-slate-400 hover:text-slate-700 dark:hover:text-white transition-colors"
                        >
                          {isCollapsed ? (
                            <ChevronRight className="w-3.5 h-3.5 text-indigo-500" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5 text-indigo-500" />
                          )}
                        </button>
                        <span className="px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800/60 flex items-center gap-1.5">
                          <span className="text-[10px] text-indigo-500">0/1</span>
                          <span>if {step.condition_expr}</span>
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            const newExpr = prompt("Edit condition expression:", step.condition_expr);
                            if (newExpr) {
                              setLiveSteps((prev) =>
                                prev.map((s, i) => (i === idx ? { ...s, condition_expr: newExpr } : s))
                              );
                              setEditedCount((prev) => prev + 1);
                            }
                          }}
                          className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                          title="Edit condition"
                        >
                          <Edit2 className="w-3 h-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteStep(idx)}
                          className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                          title="Delete condition block"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>

                    {!isCollapsed && (
                      <div className="space-y-3 pl-3 border-l-2 border-indigo-300 dark:border-indigo-700/60 ml-2.5">
                        {/* Then Branch */}
                        <div className="space-y-1.5">
                          <span className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider block flex items-center gap-1">
                            <CornerDownRight className="w-3 h-3" />
                            Then
                          </span>
                          {(step.then_steps || []).map((tStep, tIdx) => (
                            <div
                              key={tIdx}
                              className="px-3 py-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between text-xs hover:border-slate-300 dark:hover:border-slate-700 transition-all group"
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
                                {tStep.action === "navigate" ? (
                                  <Globe className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                                ) : tStep.action === "type" ? (
                                  <Type className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                                ) : (
                                  <Sparkles className="w-3.5 h-3.5 text-brand-500 shrink-0" />
                                )}
                                <span className="text-slate-800 dark:text-slate-200 font-medium truncate">
                                  {tStep.description}
                                </span>
                              </div>
                              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                  type="button"
                                  onClick={() => {
                                    const newDesc = prompt("Edit step description:", tStep.description);
                                    if (newDesc) {
                                      setLiveSteps((prev) =>
                                        prev.map((s, i) => {
                                          if (i !== idx) return s;
                                          const nextThen = [...(s.then_steps || [])];
                                          nextThen[tIdx] = { ...nextThen[tIdx], description: newDesc };
                                          return { ...s, then_steps: nextThen };
                                        })
                                      );
                                      setEditedCount((c) => c + 1);
                                    }
                                  }}
                                  className="p-1 text-slate-400 hover:text-slate-700 dark:hover:text-white"
                                >
                                  <Edit2 className="w-2.5 h-2.5" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setLiveSteps((prev) =>
                                      prev.map((s, i) => {
                                        if (i !== idx) return s;
                                        const nextThen = s.then_steps.filter((_, ti) => ti !== tIdx);
                                        return { ...s, then_steps: nextThen };
                                      })
                                    );
                                    setDeletedCount((c) => c + 1);
                                  }}
                                  className="p-1 text-slate-400 hover:text-rose-500"
                                >
                                  <Trash2 className="w-2.5 h-2.5" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Else Branch */}
                        <div className="space-y-1.5 pt-1">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1">
                              <CornerDownRight className="w-3 h-3" />
                              Else
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                setShowElseSteps((prev) => ({
                                  ...prev,
                                  [idx]: !prev[idx],
                                }))
                              }
                              className="text-[10px] text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-0.5"
                            >
                              {isElseExpanded ? "Hide steps" : "Show steps"}{" "}
                              {isElseExpanded ? "⌃" : "⌄"}
                            </button>
                          </div>

                          {isElseExpanded && (
                            <div className="space-y-1.5 pt-1">
                              {(step.else_steps || []).map((eStep, eIdx) => (
                                <div
                                  key={eIdx}
                                  className="px-3 py-2 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between text-xs"
                                >
                                  <div className="flex items-center gap-2">
                                    <Eye className="w-3.5 h-3.5 text-amber-500" />
                                    <span className="text-slate-800 dark:text-slate-200">
                                      {eStep.description}
                                    </span>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setLiveSteps((prev) =>
                                        prev.map((s, i) => {
                                          if (i !== idx) return s;
                                          const nextElse = s.else_steps.filter((_, ei) => ei !== eIdx);
                                          return { ...s, else_steps: nextElse };
                                        })
                                      );
                                      setDeletedCount((c) => c + 1);
                                    }}
                                    className="p-1 text-slate-400 hover:text-rose-500"
                                  >
                                    <Trash2 className="w-2.5 h-2.5" />
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              }

              // Standard Linear Step Card (Tracecase Studio Step Card)
              const isEditingThisStep = editingIndex === idx;

              return (
                <div
                  key={step.number || idx}
                  className="group rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80 hover:border-brand-300 dark:hover:border-brand-700 hover:shadow-sm transition-all p-2.5 space-y-1.5"
                >
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      {/* Step Number Badge */}
                      <span className="w-5 h-5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-mono text-[11px] font-bold flex items-center justify-center shrink-0">
                        {step.number || idx + 1}
                      </span>

                      {/* Expand / Collapse Chevron */}
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedSteps((prev) => ({
                            ...prev,
                            [idx]: !prev[idx],
                          }))
                        }
                        className="text-slate-400 hover:text-slate-700 dark:hover:text-white"
                      >
                        {expandedSteps[idx] ? (
                          <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5" />
                        )}
                      </button>

                      {/* Action Type Icon */}
                      {step.action_type === "navigate" || step.action === "navigate" ? (
                        <Globe className="w-3.5 h-3.5 text-sky-500 shrink-0" />
                      ) : step.action_type === "click" || step.action === "click" ? (
                        <Sparkles className="w-3.5 h-3.5 text-brand-500 shrink-0" />
                      ) : step.action_type === "type" || step.action === "type" ? (
                        <Type className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      )}

                      {/* Step Description / Inline Edit */}
                      {isEditingThisStep ? (
                        <div className="flex items-center gap-1 flex-1">
                          <input
                            type="text"
                            value={editDesc}
                            onChange={(e) => setEditDesc(e.target.value)}
                            className="w-full px-2 py-0.5 text-xs rounded bg-slate-50 dark:bg-slate-950 border border-brand-400 text-slate-900 dark:text-white focus:outline-none"
                            autoFocus
                          />
                        </div>
                      ) : (
                        <div className="flex flex-col min-w-0">
                          <span className="text-slate-800 dark:text-slate-200 font-medium truncate">
                            {step.description ||
                              `${step.action || "Action"} on ${step.target || step.selector || "element"}`}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Step Action Buttons (Inline Edit & Delete) */}
                    <div className="flex items-center gap-1 shrink-0">
                      {isEditingThisStep ? (
                        <>
                          <button
                            type="button"
                            onClick={() => saveEditStep(idx)}
                            className="p-1 rounded text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/40"
                            title="Save changes"
                          >
                            <Check className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingIndex(null)}
                            className="p-1 rounded text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                            title="Cancel edit"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => startEditStep(idx, step)}
                            className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                            title="Edit step"
                          >
                            <Edit2 className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteStep(idx)}
                            className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                            title="Delete step"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Expanded Step Details */}
                  {expandedSteps[idx] && (
                    <div className="pl-6 pt-1 text-[11px] font-mono text-slate-500 dark:text-slate-400 space-y-1 border-t border-slate-100 dark:border-slate-800 mt-1">
                      {step.selector && (
                        <div className="flex items-center gap-1.5 truncate">
                          <span className="text-slate-400 dark:text-slate-500">Selector:</span>
                          <span className="text-brand-600 dark:text-brand-300 truncate">
                            {step.selector}
                          </span>
                        </div>
                      )}
                      {step.input_value && (
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-400 dark:text-slate-500">Value:</span>
                          <span className="text-indigo-600 dark:text-indigo-300">
                            {step.input_value}
                          </span>
                        </div>
                      )}
                      {step.url && (
                        <div className="flex items-center gap-1.5 truncate">
                          <span className="text-slate-400 dark:text-slate-500">URL:</span>
                          <span className="text-sky-600 dark:text-sky-300 truncate">
                            {step.url}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Step Insertion Modal */}
          {isAddingStep && (
            <div className="p-3 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 space-y-2 animate-in slide-in-from-bottom-2 shadow-lg">
              <div className="flex items-center justify-between text-xs font-bold text-slate-900 dark:text-white">
                <span>Add Custom Step</span>
                <button
                  type="button"
                  onClick={() => setIsAddingStep(false)}
                  className="text-slate-400 hover:text-slate-700 dark:hover:text-white"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <select
                  value={newStepType}
                  onChange={(e) => setNewStepType(e.target.value)}
                  className="px-2 py-1 text-xs rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-white"
                >
                  <option value="click">Click</option>
                  <option value="type">Type / Input</option>
                  <option value="navigate">Navigate</option>
                  <option value="assert">Assert Text</option>
                </select>
                <input
                  type="text"
                  placeholder="Target selector or text"
                  value={newStepTarget}
                  onChange={(e) => setNewStepTarget(e.target.value)}
                  className="col-span-2 px-2 py-1 text-xs rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-white"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setIsAddingStep(false)}
                  className="px-2.5 py-1 text-xs rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAddManualStep}
                  className="px-3 py-1 text-xs font-bold rounded-lg bg-brand-600 text-white hover:bg-brand-500"
                >
                  Insert Step
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT PANE: EMBEDDED LOCAL BROWSER CANVAS (~58% width) ── */}
        <div className="flex-1 flex flex-col bg-slate-100 dark:bg-slate-950 overflow-hidden transition-colors">
          {/* Browser Chrome Toolbar (Google Chrome Style) */}
          <div className="bg-slate-200/80 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 p-2 space-y-1.5 shrink-0 select-none">
            {/* Tab Bar Strip */}
            <div className="flex items-center justify-between">
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
                    <Globe className="w-3 h-3 text-brand-500" />
                    <span className="truncate max-w-[160px] text-[11px] font-medium">
                      {tab.title || "New Tab"}
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
                  title="Open New Tab"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Viewport Dimension Info */}
              <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500 dark:text-slate-400 shrink-0">
                <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                  {viewportDims.width}&times;{viewportDims.height}
                </span>
                <span
                  className={`w-2 h-2 rounded-full ${
                    streamConnected ? "bg-emerald-500 animate-pulse" : "bg-slate-400"
                  }`}
                  title={streamConnected ? "Live CDP Stream Connected" : "Stream Idle"}
                />
              </div>
            </div>

            {/* Navigation & Address Bar (Chrome Omnibox) */}
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

              {/* Omnibox Address Input */}
              <form onSubmit={handleNavigateSubmit} className="flex-1 relative">
                <Lock className="w-3 h-3 absolute left-3 top-1/2 -translate-y-1/2 text-emerald-500 dark:text-emerald-400" />
                <input
                  type="text"
                  value={chromeUrl}
                  onChange={(e) => setChromeUrl(e.target.value)}
                  placeholder="Enter target URL (e.g. https://example.com or http://localhost:3000)..."
                  className="w-full pl-8 pr-14 py-1.5 text-xs font-mono rounded-full bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800 focus:outline-none focus:border-brand-500 shadow-inner transition-colors"
                />
                <button
                  type="submit"
                  className="absolute right-1 top-1 bottom-1 px-2.5 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors"
                >
                  Go
                </button>
              </form>
            </div>
          </div>

          {/* Live Screencast Viewport Container */}
          <div
            ref={viewportContainerRef}
            tabIndex={0}
            onKeyDown={handleKeyDown}
            onKeyUp={handleKeyUp}
            onPaste={handlePaste}
            className="flex-1 relative bg-slate-900 flex items-center justify-center overflow-hidden outline-none select-none cursor-crosshair"
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

            {/* Idle State Prompt */}
            {!isActive && (
              <div className="text-center p-8 space-y-4 z-10 max-w-lg">
                <div className="w-14 h-14 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-center mx-auto text-brand-500 shadow-sm">
                  <Video className="w-7 h-7" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    Local Chromium Viewport
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
                    Embedded CDP-streamed browser session running natively on this machine.
                    Sub-millisecond input response, zero cloud leakage, full cookie & auth isolation.
                  </p>
                </div>

                <div className="flex items-center justify-center gap-2 pt-1">
                  <input
                    type="text"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="Enter target URL (e.g. https://example.com)..."
                    className="px-3.5 py-2 text-xs rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-white w-80 font-mono focus:outline-none focus:border-brand-500 shadow-sm"
                  />
                  <button
                    type="button"
                    onClick={handleStart}
                    disabled={loading || !url.trim()}
                    className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold transition-all shadow-md shadow-brand-600/25 flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                  >
                    {loading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Play className="w-3.5 h-3.5 fill-current" />
                    )}
                    <span>Start Studio</span>
                  </button>
                </div>
              </div>
            )}

            {/* Connecting Spinner */}
            {isActive && !streamConnected && (
              <div className="absolute inset-0 bg-white/70 dark:bg-black/80 backdrop-blur-sm flex items-center justify-center z-20">
                <div className="flex items-center gap-3 text-xs text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-900 p-4 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800">
                  <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
                  <span>Connecting to local CDP screencast stream...</span>
                </div>
              </div>
            )}

            {/* JS Dialog Modal Overlay */}
            {activeDialog && (
              <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-40">
                <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 max-w-md w-full shadow-2xl space-y-4">
                  <div className="flex items-center gap-2.5 text-amber-500">
                    <AlertCircle className="w-5 h-5 shrink-0" />
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white capitalize">
                      JavaScript {activeDialog.dialog_type || "Dialog"}
                    </h4>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                    {activeDialog.message}
                  </p>
                  {activeDialog.dialog_type === "prompt" && (
                    <input
                      type="text"
                      value={dialogPromptValue}
                      onChange={(e) => setDialogPromptValue(e.target.value)}
                      placeholder="Enter value..."
                      className="w-full px-3 py-1.5 text-xs rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
                      autoFocus
                    />
                  )}
                  <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                    {activeDialog.dialog_type !== "alert" && (
                      <button
                        type="button"
                        onClick={() => handleDialogResponse(false)}
                        className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200"
                      >
                        Cancel
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDialogResponse(true)}
                      className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 hover:bg-brand-500 text-white"
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
                  className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl p-5 max-w-md w-full shadow-2xl space-y-4"
                >
                  <div className="flex items-center gap-2.5 text-sky-500">
                    <FileUp className="w-5 h-5 shrink-0" />
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white">File Upload Request</h4>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-300">
                    Specify the absolute path of the local file to provide:
                  </p>
                  <input
                    type="text"
                    value={fileUploadPath}
                    onChange={(e) => setFileUploadPath(e.target.value)}
                    placeholder="/path/to/local/sample.png"
                    className="w-full px-3 py-1.5 text-xs rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono"
                    autoFocus
                  />
                  <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                    <button
                      type="button"
                      onClick={() => setActiveFileChooser(null)}
                      className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-sky-600 hover:bg-sky-500 text-white"
                    >
                      Upload File
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>

          {/* Bottom Diagnostics Drawer (Themed HAR, Console, Telemetry) */}
          <div
            className={`border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col shrink-0 transition-all ${
              isDrawerCollapsed ? "h-9" : "h-44"
            }`}
          >
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActiveBottomTab("network")}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                    activeBottomTab === "network"
                      ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm border border-slate-200 dark:border-slate-700"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  Network HAR ({networkRequests.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveBottomTab("console")}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                    activeBottomTab === "console"
                      ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm border border-slate-200 dark:border-slate-700"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  Console ({consoleLogs.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveBottomTab("telemetry")}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                    activeBottomTab === "telemetry"
                      ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm border border-slate-200 dark:border-slate-700"
                      : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  }`}
                >
                  Local Performance
                </button>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 hidden sm:inline">
                  Frames: {frameCountRef.current} • Latency: {latencyMs}ms
                </span>
                <button
                  type="button"
                  onClick={() => setIsDrawerCollapsed(!isDrawerCollapsed)}
                  className="p-1 text-slate-400 hover:text-slate-700 dark:hover:text-white"
                  title={isDrawerCollapsed ? "Expand Drawer" : "Collapse Drawer"}
                >
                  {isDrawerCollapsed ? (
                    <ChevronUp className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </div>

            {!isDrawerCollapsed && (
              <div className="flex-1 overflow-y-auto p-2 font-mono text-[11px]">
                {activeBottomTab === "network" && (
                  <div className="space-y-1">
                    {networkRequests.length === 0 ? (
                      <div className="text-slate-400 dark:text-slate-500 text-center py-6">
                        No network requests captured yet.
                      </div>
                    ) : (
                      networkRequests.slice(-25).map((req, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between px-2.5 py-1 rounded bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800"
                        >
                          <div className="flex items-center gap-2 truncate">
                            <span
                              className={`px-1.5 py-0.2 text-[9px] font-bold rounded ${
                                req.status < 400
                                  ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400"
                                  : "bg-rose-50 dark:bg-rose-950 text-rose-600 dark:text-rose-400"
                              }`}
                            >
                              {req.status || 200}
                            </span>
                            <span className="text-slate-500 font-bold">
                              {req.method || "GET"}
                            </span>
                            <span className="text-slate-700 dark:text-slate-300 truncate">
                              {req.url}
                            </span>
                          </div>
                          <span className="text-slate-400 shrink-0 text-[10px]">
                            {req.duration ? `${Math.round(req.duration)}ms` : "cached"}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {activeBottomTab === "console" && (
                  <div className="space-y-1">
                    {consoleLogs.length === 0 ? (
                      <div className="text-slate-400 dark:text-slate-500 text-center py-6">
                        No console messages emitted.
                      </div>
                    ) : (
                      consoleLogs.slice(-25).map((log, i) => (
                        <div
                          key={i}
                          className={`px-2.5 py-1 rounded bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 flex items-start gap-2 ${
                            log.type === "error" ? "text-rose-600 dark:text-rose-400" : "text-slate-700 dark:text-slate-300"
                          }`}
                        >
                          <span className="text-slate-400">[{log.type || "log"}]</span>
                          <span className="break-all">{log.text}</span>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {activeBottomTab === "telemetry" && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-2 text-slate-700 dark:text-slate-300">
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800">
                      <span className="text-[10px] text-slate-400 uppercase font-sans font-bold block">
                        Local CDP Frames
                      </span>
                      <span className="text-lg font-bold text-slate-900 dark:text-white font-mono">
                        {frameCountRef.current}
                      </span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800">
                      <span className="text-[10px] text-slate-400 uppercase font-sans font-bold block">
                        Network Round-Trip
                      </span>
                      <span className="text-lg font-bold text-emerald-600 dark:text-emerald-400 font-mono">
                        {latencyMs}ms (Socket)
                      </span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800">
                      <span className="text-[10px] text-slate-400 uppercase font-sans font-bold block">
                        Execution Sandbox
                      </span>
                      <span className="text-lg font-bold text-sky-600 dark:text-sky-400 font-sans">
                        Air-Gapped
                      </span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800">
                      <span className="text-[10px] text-slate-400 uppercase font-sans font-bold block">
                        Storage Engine
                      </span>
                      <span className="text-lg font-bold text-indigo-600 dark:text-indigo-400 font-sans">
                        SQLite Local
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ──────────────────────────────────────────────────────────────────────────
          LOCAL VARIABLES SLIDE-OVER DRAWER
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
              onSubmit={handleAddVariable}
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
