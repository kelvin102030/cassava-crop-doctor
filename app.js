const photoInput = document.getElementById("leafPhoto");
const preview = document.getElementById("preview");
const message = document.getElementById("message");

photoInput.addEventListener("change", () => {
  const file = photoInput.files[0];

  if (!file) {
    preview.hidden = true;
    preview.removeAttribute("src");
    return;
  }

  if (!file.type.startsWith("image/")) {
    message.textContent = "Please choose an image file.";
    photoInput.value = "";
    return;
  }

  if (preview.dataset.url) URL.revokeObjectURL(preview.dataset.url);
  const imageUrl = URL.createObjectURL(file);
  preview.dataset.url = imageUrl;
  preview.src = imageUrl;
  preview.hidden = false;
  message.textContent = "Photo selected. AI assessment is not connected yet.";
});

document.getElementById("prepareBtn").addEventListener("click", () => {
  const file = photoInput.files[0];
  const symptom = document.getElementById("symptoms").value;

  if (!file) {
    message.textContent = "Please choose a cassava leaf photo first.";
    photoInput.click();
    return;
  }

  message.textContent = symptom
    ? "Photo prepared. Observation: " + symptom +
      ". No diagnosis has been made. The next development step is connecting and testing a real cassava disease model."
    : "Photo prepared. Select an observation if you can. No diagnosis has been made because the AI model is not connected yet.";
});
