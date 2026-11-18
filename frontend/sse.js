/* 公共 SSE 工具：POST JSON → 流式读取 → 按帧回调。
   用法：await streamSSE(url, body, { signal, onEvent })
   onEvent(event, payload)：event 取自 event: 行（缺省 'message'），payload 为 data 行的 JSON 解析结果 */
window.streamSSE = async function (url, body, { signal, onEvent } = {}) {
  /* 解析单帧：data 可跨多行拼接；无 data 或非 JSON 的帧直接丢弃 */
  const parseFrame = (frame) => {
    let event = 'message';
    let data = '';
    frame.split('\n').forEach((line) => {
      if (line.startsWith('event: ')) event = line.slice(7).trim();
      else if (line.startsWith('data: ')) data += line.slice(6);
    });
    if (!data) return null;
    try { return { event, payload: JSON.parse(data) }; } catch (e) { return null; }
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* 原样提示 */ }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // 粘包处理：完整帧以空行结尾，末尾残帧留在 buffer 等下一块
    const frames = buffer.split('\n\n');
    buffer = frames.pop();
    frames.forEach((f) => {
      const parsed = parseFrame(f);
      if (parsed && onEvent) onEvent(parsed.event, parsed.payload);
    });
  }
};
