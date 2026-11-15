// One-time microphone permission for the extension (the side panel cannot show Chrome's permission prompt).
navigator.mediaDevices.getUserMedia({ audio: true }).then(s => {
  s.getTracks().forEach(x => x.stop());
  document.getElementById("m").innerHTML = "✓ Done — close this tab and press the mic again.<br>✓ হয়েছে — এই ট্যাব বন্ধ করে আবার মাইক চাপো।";
}).catch(() => {
  document.getElementById("m").innerHTML = "Microphone was blocked. Allow it from the 🔒 icon in the address bar.<br>মাইক্রোফোন বন্ধ আছে। ঠিকানার পাশের 🔒 থেকে Allow করো।";
});
