const vendorForm = document.querySelector("#vendor-upload-form");
const finacleForm = document.querySelector("#finacle-upload-form");
const vendorMessage = document.querySelector("#vendor-message");
const finacleMessage = document.querySelector("#finacle-message");

const handleUpload = (formElement, messageElement, label) => {
  if (!formElement || !messageElement) {
    return;
  }
  formElement.addEventListener("submit", (event) => {
    event.preventDefault();

    const fileInput = formElement.querySelector('input[type="file"]');
    const file = fileInput?.files[0];

    if (!file) {
      messageElement.textContent = `Please select a ${label} file.`;
      messageElement.style.color = "#b42318";
      return;
    }

    messageElement.textContent = `${label} selected: ${file.name}. Ready to upload.`;
    messageElement.style.color = "#0f4c81";
  });
};

handleUpload(vendorForm, vendorMessage, "Vendor MIS");
handleUpload(finacleForm, finacleMessage, "Finacle MIS");
