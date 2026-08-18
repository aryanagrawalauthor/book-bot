import os
import glob
import json
import base64
import requests

STATE_FILE = ".posted_state.json"
BUFFER_API_KEY = os.environ["BUFFER_API_KEY"]
BUFFER_PROFILE_ID = os.environ["BUFFER_PROFILE_ID"]  # your Instagram channel ID in Buffer

CAPTION_MAP_FILE = "captions.json"  # optional: {"poster_01.png": "caption text..."}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"posted": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_next_poster(state):
    all_posters = sorted(glob.glob("poster_*.png"))
    for p in all_posters:
        if p not in state["posted"]:
            return p
    return None


def get_caption(poster_filename):
    if os.path.exists(CAPTION_MAP_FILE):
        with open(CAPTION_MAP_FILE) as f:
            captions = json.load(f)
        return captions.get(poster_filename, "New post from The Art of Becoming 📖")
    return "New post from The Art of Becoming 📖"


def post_to_buffer(image_path, caption):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    url = "https://api.bufferapp.com/1/updates/create.json"
    payload = {
        "access_token": BUFFER_API_KEY,
        "profile_ids[]": BUFFER_PROFILE_ID,
        "text": caption,
        "media[photo]": f"data:image/png;base64,{img_b64}",
    }
    resp = requests.post(url, data=payload)
    resp.raise_for_status()
    return resp.json()


def main():
    state = load_state()
    poster = get_next_poster(state)

    if poster is None:
        print("Queue is empty. No posters left to post. Add more poster_XX.png files to the repo root.")
        return

    caption = get_caption(poster)
    result = post_to_buffer(poster, caption)
    print("Posted:", poster, "->", result)

    state["posted"].append(poster)
    save_state(state)


if __name__ == "__main__":
    main()
