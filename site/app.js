const dialog = document.querySelector(".image-dialog");
const dialogImage = dialog?.querySelector("img");
const closeButton = dialog?.querySelector(".dialog-close");

for (const shot of document.querySelectorAll(".product-shot")) {
  shot.addEventListener("click", () => {
    if (!dialog || !dialogImage) return;
    dialogImage.src = shot.dataset.image || "";
    dialog.showModal();
  });
}

closeButton?.addEventListener("click", () => dialog?.close());
dialog?.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});
