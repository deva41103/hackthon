const chat = document.getElementById("chat");
const micBtn = document.getElementById("micBtn");
const stopAudioBtn = document.getElementById("stopAudio");

let socket, mediaRecorder, audioPlayer = new Audio();
let isRecording = false;
let audioChunks = [];

// add chat bubble
function addBubble(text, who="ai") {
  const row = document.createElement("div");
  row.className = `row ${who}`;
  const b = document.createElement("div");
  b.className = "bubble";
  b.textContent = text;
  row.appendChild(b);
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

function blobToBase64(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.readAsDataURL(blob);
  });
}

micBtn.onclick = async () => {
  if (!isRecording) {
    socket = io();

    socket.on("ai_reply", (msg) => {
      if (msg.user_text) addBubble(msg.user_text, "me");
      addBubble(msg.ai_text, "ai");
      if (msg.audio_url) {
        audioPlayer.pause();
        audioPlayer = new Audio(msg.audio_url + "?t=" + Date.now());
        audioPlayer.play();
      }
    });

    socket.on("error", (e) => addBubble("⚠️ " + e.msg, "ai"));

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.ondataavailable = async (e) => {
      const blob = new Blob([e.data], { type: "audio/webm" });
      const b64 = await blobToBase64(blob);
      socket.emit("utterance_blob", { b64, mime: blob.type });
    };

    mediaRecorder.start(3000); // send every 3s
    micBtn.textContent = "⏸ Pause Mic";
    isRecording = true;
  } else {
    mediaRecorder.stop();
    micBtn.textContent = "🎤 Start Talking";
    isRecording = false;
  }
};

stopAudioBtn.onclick = () => {
  audioPlayer.pause();
  audioPlayer.currentTime = 0;
};
