const API_URL = "https://cassava-crop-doctor-api.onrender.com/api/diagnose";

const photoInput = document.getElementById("leafPhoto");
const preview = document.getElementById("preview");
const message = document.getElementById("message");
const prepareBtn = document.getElementById("prepareBtn");

message.style.whiteSpace = "pre-line";

photoInput.addEventListener("change", () => {
  const file = photoInput.files[0];

  if (!file) {
    preview.hidden = true;
    preview.removeAttribute("src");

    if (preview.dataset.url) {
      URL.revokeObjectURL(preview.dataset.url);
      delete preview.dataset.url;
    }

    message.textContent = "";
    return;
  }

  const allowedTypes = ["image/jpeg", "image/png", "image/webp"];

  if (!allowedTypes.includes(file.type)) {
    message.textContent =
      "Please choose a JPEG, PNG, or WebP image.";
    photoInput.value = "";
    preview.hidden = true;
    return;
  }

  if (file.size > 8 * 1024 * 1024) {
    message.textContent =
      "This photo is too large. Please choose an image under 8 MB.";
    photoInput.value = "";
    preview.hidden = true;
    return;
  }

  if (preview.dataset.url) {
    URL.revokeObjectURL(preview.dataset.url);
  }

  const imageUrl = URL.createObjectURL(file);
  preview.dataset.url = imageUrl;
  preview.src = imageUrl;
  preview.hidden = false;

  message.textContent =
    "Photo selected. Choose an observation, then tap Assess cassava leaf.";
});

prepareBtn.textContent = "Assess cassava leaf";

prepareBtn.addEventListener("click", async () => {
  const file = photoInput.files[0];
  const symptom = document.getElementById("symptoms").value;

  if (!file) {
    message.textContent = "Please choose a cassava leaf photo first.";
    photoInput.click();
    return;
  }

  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    message.textContent = "Please choose a JPEG, PNG, or WebP image.";
    return;
  }

  if (file.size > 8 * 1024 * 1024) {
    message.textContent =
      "This photo is too large. Please choose an image under 8 MB.";
    return;
  }

  const formData = new FormData();
  formData.append("photo", file);
  formData.append("symptoms", symptom || "Not specified");

  prepareBtn.disabled = true;
  message.textContent =
    "Assessing your photo with AI. This may take a little while...";

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      body: formData
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(
        result.error || "The assessment could not be completed."
      );
    }

    message.textContent =
      (result.assessment || "No assessment was returned.") +
      "\n\n" +
      (result.disclaimer ||
        "Preliminary AI guidance only; not a confirmed diagnosis.");
  } catch (error) {
    console.error("Cassava assessment error:", error);

    message.textContent =
      "We could not complete the assessment. " +
      (error.message || "Please check your internet connection.") +
      "\n\nPlease try again later.";
  } finally {
    prepareBtn.disabled = false;
  }
});
