const params = new URLSearchParams(location.search);
if (params.has('green')) document.body.classList.add('green');
const bubble = document.querySelector('#bubble');
const statusText = document.querySelector('#status');
const error = document.querySelector('#error');
const button = document.querySelector('#enable');
const client = crypto.randomUUID();
let model, app, audioContext, analyser, cancelCurrent;
let enabled = false, blocked = false, muted = false, playing = false;
let speaking = false, serverId = null, epoch = 0, loopStarted = false;
let queue = [], seen = new Set();

function requireGesture(message) {
  blocked = true;
  error.textContent = message;
  button.textContent = '点此恢复欢迎声音';
  button.classList.remove('hidden');
}

async function init() {
  try {
    app = new PIXI.Application({resizeTo: window, backgroundAlpha: 0, antialias: true,
      resolution: Math.min(devicePixelRatio, 2), autoDensity: true});
    document.querySelector('#stage').appendChild(app.view);
    model = await PIXI.live2d.Live2DModel.from('/static/models/haru/haru_greeter_t03.model3.json', {autoInteract: false});
    app.stage.addChild(model);
    function layout() {
      model.scale.set(1);
      model.scale.set(Math.min(innerWidth * .93 / model.width, innerHeight * .80 / model.height));
      model.anchor.set(.5, 1);
      model.position.set(innerWidth * .5, innerHeight * 1.02);
    }
    layout();
    window.addEventListener('resize', layout);
    model.internalModel.on('beforeModelUpdate', () => {
      let mouth = 0;
      if (speaking) {
        if (analyser) {
          const data = new Uint8Array(analyser.fftSize);
          analyser.getByteTimeDomainData(data);
          mouth = Math.min(1, Math.sqrt(data.reduce((sum, v) => sum + (v - 128) ** 2, 0) / data.length) / 23);
        } else mouth = .25 + .25 * Math.sin(performance.now() / 70);
      }
      model.internalModel.coreModel.setParameterValueById('ParamMouthOpenY', mouth);
    });
    window.modelReady = true;
    statusText.textContent = 'Live2D 已就绪 · 点击启用声音';
  } catch (exc) { error.textContent = '角色加载失败：' + exc.message; }
}

button.onclick = async () => {
  if (!model) { error.textContent = '请等待角色加载完成'; return; }
  try {
    audioContext = audioContext || new AudioContext();
    await audioContext.resume();
    if (audioContext.state !== 'running') throw Error('浏览器尚未允许声音');
    const claim = await fetch('/api/player/claim',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client})});
    if (!claim.ok) throw Error('未能接管语音播放，请重试');
    enabled = true;
    blocked = false;
    error.textContent = '';
    statusText.textContent = '声音已启用，等待观众进入';
    button.classList.add('hidden');
    if (!loopStarted) { loopStarted = true; poll(); }
  } catch (exc) { requireGesture(exc.message); }
};

function cancelPlayback() {
  epoch++;
  queue = [];
  seen.clear();
  speaking = false;
  if (cancelCurrent) cancelCurrent();
  speechSynthesis.cancel();
  bubble.classList.remove('show');
}

async function report(event, phase, detail = '') {
  for (let n = 0; n < 2; n++) {
    try {
      const response = await fetch('/api/playback', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({client, event: event.id, attempt: event.attempt || 1, phase, detail: detail.slice(0, 180)})});
      if (!response.ok) throw Error('播放回报未确认 (' + response.status + ')');
      return;
    } catch (exc) {
      if (n === 1) throw exc;
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  }
}

async function poll() {
  try {
    const response = await fetch('/api/events?client=' + client + '&ready=' + !blocked);
    if (!response.ok) throw Error('服务暂不可用');
    const state = await response.json();
    if (serverId && state.server_id !== serverId) cancelPlayback();
    serverId = state.server_id;
    if (state.busy) {
      if (playing) cancelPlayback();
      error.textContent = '另一个角色窗口正在播放，请关闭它，最多等待 30 秒。';
    } else {
      if (error.textContent.startsWith('另一个角色窗口') || error.textContent.startsWith('本地服务连接中断')) error.textContent = '';
      if (state.muted && !muted) cancelPlayback();
      muted = state.muted;
      if (muted) statusText.textContent = '欢迎已暂停';
      for (const event of state.events) {
        const key = event.id + ':' + (event.attempt || 1);
        if (!seen.has(key)) { seen.add(key); queue.push(event); }
      }
      drain();
    }
  } catch (exc) {
    error.textContent = '本地服务连接中断，正在重试…';
  } finally { setTimeout(poll, 700); }
}

async function playAudio(url, onStart) {
  await audioContext.resume();
  if (audioContext.state !== 'running') throw new DOMException('请点击恢复欢迎声音', 'NotAllowedError');
  return new Promise((resolve, reject) => {
    const audio = new Audio(url);
    audio.volume = 1;
    const source = audioContext.createMediaElementSource(audio);
    const meter = audioContext.createAnalyser();
    meter.fftSize = 256;
    analyser = meter;
    source.connect(meter); meter.connect(audioContext.destination);
    let settled = false;
    const timer = setTimeout(() => finish(Error('语音播放超时')), 30000);
    const cancel = () => finish(new DOMException('播放已取消', 'AbortError'));
    cancelCurrent = cancel;
    function finish(exc) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      audio.pause(); source.disconnect(); meter.disconnect(); analyser = null;
      if (cancelCurrent === cancel) cancelCurrent = null;
      exc ? reject(exc) : resolve();
    }
    audio.onended = () => finish();
    audio.onerror = () => finish(Error('语音文件播放失败'));
    audio.play().then(() => { speaking = true; onStart(); }).catch(finish);
  });
}

async function browserSpeech(text, onStart) {
  return new Promise((resolve, reject) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'zh-CN';
    utterance.voice = speechSynthesis.getVoices().find(voice => voice.lang === 'zh-CN') || null;
    let settled = false;
    const timer = setTimeout(() => {
      finish(Error('本机语音超时，未确认播放'));
      speechSynthesis.cancel();
    }, 20000);
    const cancel = () => finish(new DOMException('播放已取消', 'AbortError'));
    cancelCurrent = cancel;
    function finish(exc) {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (cancelCurrent === cancel) cancelCurrent = null;
      exc ? reject(exc) : resolve();
    }
    utterance.onstart = () => { speaking = true; onStart(); };
    utterance.onend = () => finish();
    utterance.onerror = event => finish(event.error === 'not-allowed'
      ? new DOMException('请点击恢复欢迎声音', 'NotAllowedError') : Error('本机语音失败：' + event.error));
    speechSynthesis.speak(utterance);
  });
}

async function drain() {
  if (playing || !queue.length || muted || blocked) return;
  playing = true;
  const event = queue.shift(), token = epoch;
  const key = event.id + ':' + (event.attempt || 1);
  try {
    bubble.textContent = event.text;
    bubble.classList.add('show');
    const action = {gift:'正在播报礼物…',chat:'正在朗读评论…',like:'正在感谢点赞…'}[event.kind];
    statusText.textContent = action || (event.people > 1 ? '正在欢迎 ' + event.people + ' 位朋友…' : '正在欢迎…');
    model.motion('Tap', 0, 3);
    let started = false;
    const onStart = () => {
      if (!started) { started = true; report(event, 'started').catch(() => {}); }
    };
    if (event.audio) {
      try { await playAudio(event.audio, onStart); }
      catch (exc) {
        if (exc.name === 'NotAllowedError' || exc.name === 'AbortError') throw exc;
        await browserSpeech(event.text, onStart);
      }
    } else await browserSpeech(event.text, onStart);
    if (token !== epoch) return;
    await report(event, 'finished');
    window.lastWelcome = event.text;
    error.textContent = '';
    statusText.textContent = '浏览器已完成欢迎播放';
  } catch (exc) {
    if (token !== epoch || exc.name === 'AbortError') return;
    const isBlocked = exc.name === 'NotAllowedError';
    if (isBlocked) requireGesture('声音被浏览器阻止，请点击恢复。待播欢迎会保留。');
    else { error.textContent = '声音未播放：' + exc.message; statusText.textContent = '播放失败，将重试一次'; }
    try { await report(event, isBlocked ? 'blocked' : 'failed', exc.name + ': ' + exc.message); }
    catch (reportError) { error.textContent += '；' + reportError.message; }
    seen.delete(key);
  } finally {
    speaking = false; bubble.classList.remove('show'); playing = false;
    if (seen.size > 300) { seen.clear(); seen.add(key); }
    setTimeout(drain, 100);
  }
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && enabled && audioContext) audioContext.resume().catch(() => {});
});
window.addEventListener('pagehide', () => {
  navigator.sendBeacon('/api/player/release',new Blob([JSON.stringify({client})],{type:'application/json'}));
});
init();
