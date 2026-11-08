// The companion on the desktop: one VRM character and all of its motion.
//
// Every motion is code: a function of time that turns humanoid bones and sets
// expression weights. Each frame adds, in this order, the ambient motion, the
// state motion (waiting or dozing), the one motion that plays (a gesture,
// "think" or an exercise step) and the mouth, on top of the rest pose.
//
// Python drives the page through window.cognia and hears back through the
// "host" object of the web channel: pageReady() once the character stands, and
// pageFailed(reason) if it cannot be drawn.

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const DEG = Math.PI / 180;
// The upper arms turn down this far from the T-pose for the rest pose.
const REST_ARM = 75;
// Turning an upper arm up on Z: positive for the left arm, negative for the right.
const ARM = { left: 1, right: -1 };
const FACES = ['neutral', 'relaxed', 'happy', 'sad', 'surprised'];
const SHAPES = ['aa', 'ih', 'ou', 'ee', 'oh'];
const FACE_CHANGE_S = 0.3;
const MOUTH_FOLLOW_S = 0.06;
const MOUTH_GAIN = 1.3;
const STOP_S = 0.5;
const BONES = [
  'hips', 'spine', 'chest', 'neck', 'head',
  'leftShoulder', 'rightShoulder', 'leftUpperArm', 'rightUpperArm',
  'leftLowerArm', 'rightLowerArm', 'leftHand', 'rightHand',
];

// ── small helpers ──────────────────────────────────────────────────────────

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => { const u = clamp01(x); return u * u * (3 - 2 * u); };
const easeOut = (x) => { const u = clamp01(x); return 1 - (1 - u) * (1 - u); };
const rand = (low, high) => low + Math.random() * (high - low);
// One dip from 0 up to 1 and back to 0 as x runs from 0 to 1.
const dip = (x) => (x <= 0 || x >= 1 ? 0 : Math.sin(Math.PI * x) ** 2);
// Into a pose over `rise` seconds, hold, and out over the last `fall` seconds.
const into = (t, length, rise, fall) =>
  t <= 0 || t >= length ? 0 : Math.min(smooth(t / rise), smooth((length - t) / fall));
// Toward a target at a rate that does not depend on the frame rate.
const follow = (now, target, dt, seconds) => now + (target - now) * (1 - Math.exp(-dt / seconds));
const toward = (now, target, dt, seconds) =>
  target > now ? Math.min(target, now + dt / seconds) : Math.max(target, now - dt / seconds);

// Offsets from the rest pose, in degrees, and expression weights for one frame.
class Pose {
  constructor() {
    this.bones = new Map();
    this.faces = new Map();
    this.yaw = 0;
    this.pitch = 0;
    this.hipsY = 0;
    this.centreGaze = 0;
  }
  turn(bone, x = 0, y = 0, z = 0) {
    const offset = this.bones.get(bone) || [0, 0, 0];
    offset[0] += x; offset[1] += y; offset[2] += z;
    this.bones.set(bone, offset);
  }
  face(name, weight) {
    this.faces.set(name, Math.max(this.faces.get(name) || 0, weight));
  }
  look(yaw, pitch) { this.yaw += yaw; this.pitch += pitch; }
  add(other, k) {
    for (const [bone, [x, y, z]] of other.bones) this.turn(bone, x * k, y * k, z * k);
    for (const [name, weight] of other.faces) this.face(name, weight * k);
    this.look(other.yaw * k, other.pitch * k);
    this.hipsY += other.hipsY * k;
    this.centreGaze = Math.max(this.centreGaze, other.centreGaze * k);
  }
}

// Head down is positive X; turning to the character's left is positive Y;
// tilting to its right shoulder is positive Z; gaze up is positive pitch.
const nod = (pose, degrees) => pose.turn('head', degrees);
const tilt = (pose, degrees) => pose.turn('head', 0, 0, degrees);
const raiseArm = (pose, side, degrees) => pose.turn(`${side}UpperArm`, 0, 0, degrees * ARM[side]);

// ── ambient motion: blink, breathe, sway, gaze ─────────────────────────────

const ambient = {
  rate: rand(0.2, 0.3),
  phase: 0,
  nextBlink: 1,
  blinkAt: -10,
  doubleBlink: false,
  posture: [0, 0, 0, 0],
  postureTarget: [0, 0, 0, 0],
  nextPosture: 0,
  gaze: [0, 0],
  gazeTarget: [0, 0],
  nextGaze: 0,
  pointer: null,
};

function blinkCurve(x) {
  if (x < 0 || x > 0.15) return 0;
  return x < 0.06 ? x / 0.06 : 1 - (x - 0.06) / 0.09;
}

function addAmbient(pose, t, dt, breath) {
  if (t >= ambient.nextBlink) {
    ambient.blinkAt = t;
    ambient.doubleBlink = Math.random() < 0.1;
    ambient.nextBlink = t + rand(2, 6);
  }
  const since = t - ambient.blinkAt;
  pose.face('blink', blinkCurve(since) + (ambient.doubleBlink ? blinkCurve(since - 0.25) : 0));

  ambient.phase += dt * breath.rate * 2 * Math.PI;
  const lift = Math.sin(ambient.phase) * breath.scale;
  pose.turn('spine', -0.6 * lift);
  pose.turn('chest', -1.0 * lift);

  if (t >= ambient.nextPosture) {
    ambient.postureTarget = [rand(-1.2, 1.2), rand(-2, 2), rand(-1.5, 1.5), rand(-1, 1)];
    ambient.nextPosture = t + rand(10, 30);
  }
  ambient.posture = ambient.posture.map((value, i) => follow(value, ambient.postureTarget[i], dt, 3));
  const [hipsTilt, neckTurn, neckTilt, spineTilt] = ambient.posture;
  pose.turn('hips', 0, 0, hipsTilt + 0.4 * Math.sin(t * 0.37));
  pose.turn('neck', 0, neckTurn + 0.5 * Math.sin(t * 0.23), neckTilt);
  pose.turn('spine', 0, 0, spineTilt);

  if (ambient.pointer) {
    ambient.gazeTarget = [ambient.pointer[0] * 20, ambient.pointer[1] * 12];
  } else if (t >= ambient.nextGaze) {
    ambient.gazeTarget = [rand(-6, 6), rand(-3, 3)];
    ambient.nextGaze = t + rand(1, 3);
  }
  ambient.gaze = ambient.gaze.map((value, i) => follow(value, ambient.gazeTarget[i], dt, 0.08));
  pose.look(ambient.gaze[0] * breath.gaze, ambient.gaze[1] * breath.gaze);
}

// ── state motion: waiting and dozing ───────────────────────────────────────

const state = {
  name: 'active',
  waiting: 0,
  side: 0,
  sideNow: 0,
  holdUntil: 0,
  dozeEyes: 0,
  dozeHead: 0,
  nextDrop: 0,
  dropAt: -10,
};

function updateState(t, dt) {
  const waiting = state.name === 'waiting';
  const dozing = state.name === 'dozing';
  state.waiting = toward(state.waiting, waiting ? 1 : 0, dt, 0.6);
  state.dozeEyes = toward(state.dozeEyes, dozing ? 1 : 0, dt, dozing ? 1.5 : 0.5);
  state.dozeHead = toward(state.dozeHead, dozing ? 1 : 0, dt, dozing ? 2.0 : 0.8);
  if (waiting && t >= state.holdUntil) {
    if (state.side === 0) {
      state.side = Math.random() < 0.5 ? -1 : 1;
      state.holdUntil = t + rand(3, 6);
    } else {
      state.side = 0;
      state.holdUntil = t + rand(2, 4);
    }
  }
  if (!waiting) state.side = 0;
  state.sideNow = follow(state.sideNow, state.side, dt, 0.35);
  if (dozing && t >= state.nextDrop) {
    state.dropAt = t;
    state.nextDrop = t + rand(20, 40);
  }
}

function addState(pose, t) {
  const wait = state.waiting * state.sideNow;
  pose.look(25 * wait, 0);
  pose.turn('neck', 0, 10 * wait);

  const since = t - state.dropAt;
  const drop = since < 0.3 ? smooth(since / 0.3) : 1 - smooth((since - 0.3) / 1.0);
  nod(pose, (20 + 5 * Math.max(0, drop)) * state.dozeHead);
  pose.turn('neck', 5 * state.dozeHead);
  pose.face('blink', state.dozeEyes);
}

function breathFor(motion) {
  const doze = state.dozeHead;
  const held = motion && motion.stopsBreath ? motion.stopsBreath() : 0;
  return {
    rate: ambient.rate + (0.15 - ambient.rate) * doze,
    scale: 1.5 * (1 + doze) * (1 - held),
    gaze: (1 - state.waiting) * (1 - doze),
  };
}

// ── gestures, think and exercises ──────────────────────────────────────────

// Each one-shot motion: its length in seconds and what it does at time t.
const GESTURES = {
  nod: {
    length: 1.2,
    play(pose, t) { nod(pose, 15 * dip((t % 0.6) / 0.6)); },
  },
  bow: {
    length: 1.8,
    play(pose, t) {
      const k = t < 0.6 ? smooth(t / 0.6) : t < 1.1 ? 1 : 1 - smooth((t - 1.1) / 0.7);
      pose.turn('spine', 15 * k);
      pose.turn('chest', 10 * k);
      nod(pose, 10 * k);
      pose.look(0, -10 * k);
    },
  },
  sheepish: {
    length: 1.5,
    play(pose, t) {
      const k = t < 0.4 ? smooth(t / 0.4) : t < 1.1 ? 1 : 1 - smooth((t - 1.1) / 0.4);
      tilt(pose, 10 * k);
      nod(pose, 8 * k);
      pose.look(0, -12 * k);
      pose.face('relaxed', 0.3 * k);
    },
  },
  comfort: {
    length: 2.0,
    play(pose, t) {
      const k = into(t, 2.0, 0.3, 0.4);
      tilt(pose, 8 * k);
      nod(pose, 10 * dip((t - 0.5) / 1.0));
      pose.face('blink', 0.3 * k);
      pose.centreGaze = k;
    },
  },
  cheer: {
    length: 1.5,
    play(pose, t) {
      const k = t < 0.3 ? smooth(t / 0.3) : t < 1.0 ? 1 : 1 - smooth((t - 1.0) / 0.5);
      for (const side of ['left', 'right']) {
        raiseArm(pose, side, 60 * k);
        pose.turn(`${side}LowerArm`, 0, -30 * k * ARM[side]);
      }
      pose.hipsY += 0.02 * dip(((t - 0.2) % 0.4) / 0.4) * (t > 0.2 && t < 1.0 ? 1 : 0);
      pose.face('happy', k);
    },
  },
  wave: {
    length: 2.1,
    play(pose, t) {
      const k = t < 0.4 ? smooth(t / 0.4) : t < 1.6 ? 1 : 1 - smooth((t - 1.6) / 0.5);
      raiseArm(pose, 'right', 70 * k);
      pose.turn('rightLowerArm', 0, 0, 90 * k * ARM.right);
      const waving = t > 0.4 && t < 1.6 ? Math.sin(2 * Math.PI * 3 * (t - 0.4) / 1.2) : 0;
      // Turn the palm from the T-pose, where it faces down, to face the user.
      pose.turn('rightHand', -90 * k, 0, 20 * waving * k);
      pose.face('happy', 0.5 * k);
    },
  },
};

function thinkMotion(start) {
  const motion = {
    name: 'think',
    start,
    ending: null,
    side: 1,
    sideNow: 0,
    switchAt: start + rand(1.5, 2.5),
    nextBlink: start + rand(2.5, 4),
    blinkAt: -10,
    play(pose, t, dt) {
      if (t >= this.switchAt) {
        this.side = -this.side;
        this.switchAt = t + rand(1.5, 2.5);
      }
      if (t >= this.nextBlink) {
        this.blinkAt = t;
        this.nextBlink = t + rand(3, 5);
      }
      this.sideNow = follow(this.sideNow, this.side, dt, 0.4);
      const into_ = smooth((t - this.start) / 0.3);
      const out = this.ending === null ? 1 : 1 - smooth((t - this.ending) / 0.3);
      const k = into_ * out;
      pose.look(15 * this.sideNow * k, 15 * k);
      tilt(pose, -8 * this.sideNow * k);
      pose.face('blink', 0.9 * dip((t - this.blinkAt) / 0.4) * k);
      if (this.ending !== null) nod(pose, 8 * dip((t - this.ending - 0.2) / 0.6));
    },
    done(t) { return this.ending !== null && t - this.ending > 0.8; },
  };
  return motion;
}

function gestureMotion(name, start) {
  const gesture = GESTURES[name];
  return {
    name,
    start,
    play(pose, t) { gesture.play(pose, t - this.start); },
    done(t) { return t - this.start >= gesture.length; },
  };
}

// The step of an exercise, from its own start time.
const STEPS = {
  'breathe in': (pose, x) => breatheIn(pose, smooth(x / 4)),
  hold: (pose) => breatheIn(pose, 1),
  'breathe out': (pose, x) => {
    breatheIn(pose, 1 - easeOut(x / 6));
    pose.face('blink', 0.5 * smooth((x - 4) / 2));
  },
  'reach up': (pose, x) => {
    const u = x % 10;
    const k = u < 3 ? smooth(u / 3) : u < 7 ? 1 : 1 - smooth((u - 7) / 3);
    for (const side of ['left', 'right']) raiseArm(pose, side, 150 * k);
  },
  'roll your shoulders': (pose, x) => {
    const k = into(x, 20, 1, 1);
    const angle = 2 * Math.PI * x / 4;
    for (const side of ['left', 'right']) {
      pose.turn(`${side}Shoulder`, 8 * Math.cos(angle) * k, 0, 8 * Math.sin(angle) * k * ARM[side]);
    }
  },
  'turn your head slowly': (pose, x) => {
    const turn = keyframes(x % 10, HEAD_TURN);
    pose.turn('head', 0, turn * 0.7);
    pose.turn('neck', 0, turn * 0.3);
  },
  'stretch your wrists': (pose, x) => {
    const k = into(x, 20, 1.5, 1.5);
    for (const side of ['left', 'right']) {
      pose.turn(`${side}UpperArm`, 0, -80 * k * ARM[side], REST_ARM * k * ARM[side]);
      pose.turn(`${side}Hand`, 0, 0, 40 * Math.sin(2 * Math.PI * x / 5) * k);
    }
  },
};

// Left, hold, right, hold, back to the centre, in one cycle of 10 s.
const HEAD_TURN = [[0, 0], [2, 35], [4, 35], [6.5, -35], [8.5, -35], [10, 0]];

// The value at x between [time, value] key frames, eased from one to the next.
function keyframes(x, frames) {
  for (let i = 1; i < frames.length; i += 1) {
    const [t0, v0] = frames[i - 1];
    const [t1, v1] = frames[i];
    if (x <= t1) return v0 + (v1 - v0) * smooth((x - t0) / (t1 - t0));
  }
  return frames[frames.length - 1][1];
}

function breatheIn(pose, k) {
  pose.turn('chest', -4 * k);
  for (const side of ['left', 'right']) raiseArm(pose, side, 5 * k);
}

function activityMotion(name, label, start) {
  const step = STEPS[label];
  return {
    name,
    label,
    start,
    activity: true,
    play(pose, t) { if (step) step(pose, t - this.start); },
    stopsBreath() { return name === 'breathing' ? 1 : 0; },
    done() { return false; },
  };
}

// ── the scene ──────────────────────────────────────────────────────────────

let host = null;
let vrm = null;
let renderer = null;
let scene = null;
let camera = null;
let restHipsY = 0;
let clock = 0;
let frameLimit = 30;
let lastFrame = 0;
let motion = null;
let stopping = null;
const faceNow = Object.fromEntries(FACES.map((name) => [name, name === 'neutral' ? 1 : 0]));
const faceTarget = { ...faceNow };
const mouthNow = Object.fromEntries(SHAPES.map((name) => [name, 0]));
const mouthTarget = { ...mouthNow };
const rest = {
  leftUpperArm: [0, 0, -REST_ARM * ARM.left],
  rightUpperArm: [0, 0, -REST_ARM * ARM.right],
};

function setUp() {
  renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.setSize(window.innerWidth, window.innerHeight);
  document.body.appendChild(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(28, window.innerWidth / window.innerHeight, 0.1, 20);
  const light = new THREE.DirectionalLight(0xffffff, Math.PI);
  light.position.set(0.5, 1.5, 2).normalize();
  scene.add(light);
  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  window.addEventListener('resize', () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
  });
}

function frameCamera() {
  const head = new THREE.Vector3();
  vrm.humanoid.getNormalizedBoneNode('head').getWorldPosition(head);
  const top = head.y + 0.2;
  const bottom = head.y - 1.05;
  const centre = (top + bottom) / 2;
  const distance = (top - bottom) / 2 / Math.tan((camera.fov * DEG) / 2);
  camera.position.set(0, centre, distance);
  camera.lookAt(0, centre, 0);
}

async function load(url) {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  const gltf = await loader.loadAsync(url);
  vrm = gltf.userData.vrm;
  if (!vrm) throw new Error('The file holds no VRM character.');
  VRMUtils.removeUnnecessaryVertices(gltf.scene);
  VRMUtils.combineSkeletons(gltf.scene);
  VRMUtils.rotateVRM0(vrm);
  vrm.scene.traverse((node) => { node.frustumCulled = false; });
  scene.add(vrm.scene);
  restHipsY = vrm.humanoid.getNormalizedBoneNode('hips').position.y;
  applyPose(new Pose(), 0);
  vrm.update(0);
  frameCamera();
}

function applyPose(pose, dt) {
  for (const name of BONES) {
    const node = vrm.humanoid.getNormalizedBoneNode(name);
    if (!node) continue;
    const base = rest[name] || [0, 0, 0];
    const offset = pose.bones.get(name) || [0, 0, 0];
    node.rotation.set((base[0] + offset[0]) * DEG, (base[1] + offset[1]) * DEG, (base[2] + offset[2]) * DEG);
  }
  vrm.humanoid.getNormalizedBoneNode('hips').position.y = restHipsY + pose.hipsY;

  const keep = 1 - pose.centreGaze;
  if (vrm.lookAt) {
    vrm.lookAt.yaw = pose.yaw * keep;
    vrm.lookAt.pitch = pose.pitch * keep;
  }
  const manager = vrm.expressionManager;
  if (!manager) return;
  for (const name of FACES) {
    faceNow[name] = toward(faceNow[name], faceTarget[name], dt, FACE_CHANGE_S);
    manager.setValue(name, Math.max(faceNow[name], pose.faces.get(name) || 0));
  }
  for (const name of SHAPES) {
    mouthNow[name] = follow(mouthNow[name], mouthTarget[name], dt, MOUTH_FOLLOW_S);
    manager.setValue(name, mouthNow[name]);
  }
  manager.setValue('blink', clamp01(pose.faces.get('blink') || 0));
}

function step(dt) {
  clock += dt;
  updateState(clock, dt);
  const pose = new Pose();
  addAmbient(pose, clock, dt, breathFor(motion));
  addState(pose, clock);
  if (motion) {
    motion.play(pose, clock, dt);
    if (motion.done(clock)) motion = null;
  }
  if (stopping) {
    const k = 1 - smooth((clock - stopping.start) / STOP_S);
    if (k <= 0) {
      stopping = null;
    } else {
      const fading = new Pose();
      stopping.motion.play(fading, stopping.frozenAt, 0);
      pose.add(fading, k);
    }
  }
  applyPose(pose, dt);
  vrm.update(dt);
}

function frame(now) {
  requestAnimationFrame(frame);
  if (!vrm) return;
  const elapsed = now - lastFrame;
  if (elapsed < 1000 / frameLimit - 1) return;
  lastFrame = now;
  step(Math.min(0.1, elapsed / 1000));
  renderer.render(scene, camera);
}

// Ends the motion that plays now and blends it back to the rest pose.
function stopMotion() {
  if (!motion) return;
  stopping = { motion, frozenAt: clock, start: clock };
  motion = null;
}

// ── what Python calls ──────────────────────────────────────────────────────

window.cognia = {
  setExpression(preset, weight) {
    for (const name of FACES) faceTarget[name] = name === preset ? clamp01(weight) : 0;
  },
  setAmbient(name) { state.name = name; },
  // A motion that arrives while another plays is dropped.
  playGesture(name) {
    if (motion || !GESTURES[name]) return false;
    motion = gestureMotion(name, clock);
    return true;
  },
  startThink() {
    if (motion) return false;
    motion = thinkMotion(clock);
    return true;
  },
  endThink() {
    if (motion && motion.name === 'think' && motion.ending === null) motion.ending = clock;
  },
  activityStep(name, label) {
    if (motion && !motion.activity) motion = null;
    motion = activityMotion(name, label, clock);
  },
  stopActivity() {
    if (motion && motion.activity) stopMotion();
  },
  setMouth(weights) {
    // Opened wider than the weights, so speech shows at the size of the window.
    for (const name of SHAPES) mouthTarget[name] = clamp01((weights[name] || 0) * MOUTH_GAIN);
  },
  lookAt(x, y) { ambient.pointer = x === null ? null : [x, y]; },
  setFrameLimit(frames) { frameLimit = Math.max(1, frames); },
};

function report(method, ...args) {
  if (host) host[method](...args);
}

setUp();
requestAnimationFrame(frame);
const channel = new Promise((resolve) => {
  new QWebChannel(qt.webChannelTransport, (ch) => { host = ch.objects.host; resolve(); });
});
const url = new URLSearchParams(location.search).get('vrm');
Promise.all([channel, load(url)])
  .then(() => report('pageReady'))
  .catch((error) => channel.then(() => report('pageFailed', String(error && error.message || error))));
