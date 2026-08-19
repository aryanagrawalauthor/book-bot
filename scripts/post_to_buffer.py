import os
import glob
import json
import requests

STATE_FILE = ".posted_state.json"
BUFFER_API_KEY = os.environ["BUFFER_API_KEY"]
BUFFER_CHANNEL_ID = os.environ["BUFFER_CHANNEL_ID"]  # your Instagram channel ID in Buffer
GITHUB_REPO = "aryanagrawalauthor/book-bot"
BRANCH = "main"

CAPTION_MAP_FILE = "captions.json"
API_URL = "https://api.buffer.com"


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


def raw_url(filename):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}/{filename}"


def post_to_buffer(image_url, caption):
    query = """
    mutation($text: String!, $channelId: String!, $mediaUrl: String!) {
      createPost(input: {
        text: $text
        channelId: $channelId
        schedulingType: automatic
        mode: addToQueue
        media: { photos: [{ url: $mediaUrl }] }
      }) {
        ... on PostActionSuccess {
          post { id text status }
        }
        ... on MutationError {
          message
        }
      }
    }
    """
    variables = {
        "text": caption,
        "channelId": BUFFER_CHANNEL_ID,
        "mediaUrl": image_url,
    }
    resp = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BUFFER_API_KEY}",
        },
        json={"query": query, "variables": variables},
    )
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data, indent=2))
    return data


def main():
    state = load_state()
    poster = get_next_poster(state)

    if poster is None:
        print("Queue is empty. Add more poster_XX.png files to the repo root.")
        return

    caption = get_caption(poster)
    image_url = raw_url(poster)
    post_to_buffer(image_url, caption)

    state["posted"].append(poster)
    save_state(state)


if __name__ == "__main__":
    main()
