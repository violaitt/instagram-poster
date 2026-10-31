import os
import textwrap
import time
from fastapi import BackgroundTasks, FastAPI
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
import requests

app = FastAPI()

os.makedirs("temp_media", exist_ok=True)
app.mount("/media", StaticFiles(directory="temp_media"), name="media")

IG_USER_ID = os.getenv("IG_USER_ID", "17841438360187312")
ACCESS_TOKEN = os.getenv(
    "ACCESS_TOKEN",
    "EAApvtNhyUiABS5h5XwgxQmXjZCN1v5R1hOY4sG2m1EZAZC5ZBaQMPTrkDBXPXMr8CfBb7z5cfnsYZCQqmcZBuk9Vt5N7VIbePeg2iTfrPUZBrmXZC1hzPEYqZBVkbK2FmQDZCu9YNuwMZAzTE0BbwhdS6XcxIbLyEIiM3am71GfOK2ZB1XbSXZBZBFnybsOfbfx5ZBPXQKYoo0nDZBZAALjxTd2ii31Ul91Xj7NsSng09vhJz",
)
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "")


class PostPayload(BaseModel):
  text: str = ""
  photos: list[str] = []


def pad_image_for_instagram(
    input_path: str, output_path: str, target_ratio: float = 4 / 5
):
  with Image.open(input_path) as img:
    img = img.convert("RGB")
    w, h = img.size
    current_ratio = w / h

    if current_ratio > target_ratio:
      new_w = w
      new_h = int(w / target_ratio)
      offset = (0, (new_h - h) // 2)
    else:
      new_w = int(h * target_ratio)
      new_h = h
      offset = ((new_w - w) // 2, 0)

    canvas = Image.new("RGB", (new_w, new_h), (0, 0, 0))
    canvas.paste(img, offset)

    if new_w > 1080:
      resize_h = int(1080 / target_ratio)
      canvas = canvas.resize((1080, resize_h), Image.Resampling.LANCZOS)

    canvas.save(output_path, "JPEG", quality=95)


def create_quote_card(text: str, output_path: str):
  target_size = (1080, 1350)
  img = Image.new("RGB", target_size, color=(15, 15, 15))
  draw = ImageDraw.Draw(img)

  font = ImageFont.load_default()
  lines = []
  for paragraph in text.split("\n"):
    if not paragraph.strip():
      lines.append("")
      continue
    lines.extend(textwrap.wrap(paragraph, width=28))

  line_spacing = 16
  total_height = len(lines) * (24 + line_spacing)
  y = (target_size[1] - total_height) // 2

  for line in lines:
    if line:
      bbox = draw.textbbox((0, 0), line, font=font)
      w = bbox[2] - bbox[0]
      draw.text(
          ((target_size[0] - w) // 2, y), line, font=font, fill=(240, 240, 240)
      )
    y += 24 + line_spacing

  brand = "PH. NINETEEN"
  draw.text((450, target_size[1] - 100), brand, font=font, fill=(110, 110, 110))
  img.save(output_path, "JPEG", quality=95)


def publish_task(payload: PostPayload):
  local_files = []
  try:
    public_urls = []
    base_endpoint = BASE_URL.rstrip("/")

    if not payload.photos and payload.text.strip():
      filename = f"quote_{int(time.time())}.jpg"
      filepath = os.path.join("temp_media", filename)
      create_quote_card(payload.text, filepath)
      local_files.append(filepath)
      public_urls.append(f"{base_endpoint}/media/{filename}")
    else:
      for idx, url in enumerate(payload.photos[:10]):
        temp_raw = f"temp_media/raw_{int(time.time())}_{idx}.jpg"
        temp_out = f"temp_media/ready_{int(time.time())}_{idx}.jpg"

        r = requests.get(url, timeout=30)
        with open(temp_raw, "wb") as f:
          f.write(r.content)

        pad_image_for_instagram(temp_raw, temp_out)
        if os.path.exists(temp_raw):
          os.remove(temp_raw)

        local_files.append(temp_out)
        fname = os.path.basename(temp_out)
        public_urls.append(f"{base_endpoint}/media/{fname}")

    if not public_urls:
      return

    caption = payload.text[:2100]

    if len(public_urls) == 1:
      res = requests.post(
          f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media",
          data={
              "image_url": public_urls[0],
              "caption": caption,
              "access_token": ACCESS_TOKEN,
          },
      ).json()
      creation_id = res.get("id")
    else:
      child_ids = []
      for purl in public_urls:
        c_res = requests.post(
            f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media",
            data={
                "image_url": purl,
                "is_carousel_item": "true",
                "access_token": ACCESS_TOKEN,
            },
        ).json()
        if "id" in c_res:
          child_ids.append(c_res["id"])

      res = requests.post(
          f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media",
          data={
              "media_type": "CAROUSEL",
              "caption": caption,
              "children": ",".join(child_ids),
              "access_token": ACCESS_TOKEN,
          },
      ).json()
      creation_id = res.get("id")

    if creation_id:
      time.sleep(6)
      requests.post(
          f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish",
          data={"creation_id": creation_id, "access_token": ACCESS_TOKEN},
      )
  finally:
    for f in local_files:
      if os.path.exists(f):
        os.remove(f)


@app.post("/publish")
def trigger(payload: PostPayload, background_tasks: BackgroundTasks):
  background_tasks.add_task(publish_task, payload)
  return {"status": "started"}


@app.get("/")
def ping():
  return {"status": "ok"}
