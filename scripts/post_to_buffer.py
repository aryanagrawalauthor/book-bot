"""
Posts one quote-poster to Instagram via Buffer's CURRENT GraphQL API.
(The old REST API at api.bufferapp.com/1/... is closed to new developers
 -- that's what caused the 401 error. This uses https://api.buffer.com instead.)

Reads a manifest.json (list of {image_url, caption}) and a state file
(posted_index.txt) to know which quote to post next each time this runs.

Required GitHub Actions secret: MY_BOOK_API_KEY
  -> Repo Settings > Secrets and variables > Actions
  -> Confirm MY_BOOK_API_KEY is listed there with your Buffer personal API key as the value.
  Never hardcode the key in this file or commit it to the repo.
"""
import os
import sys
import json
import requests

API_URL = "https://api.buffer.com"
ORGANIZATION_ID = "6a8458d6c58a52fcf4e3ba30"   # "My Organization"
# Channel ID comes from the BUFFER_CHANNEL_ID secret (set in the workflow env).
# Falls back to your Instagram channel (aryn.agrawal) if that secret isn't set.
CHANNEL_ID = os.environ.get("BUFFER_CHANNEL_ID", "6a845c4accaf649a67cbe826")

MANIFEST_PATH = "manifest.json"        # [{ "image_url": "...", "caption": "..." }, ...]
STATE_PATH = ".posted_state.json"      # matches the workflow's commit step

CREATE_POST_MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on Post {
      id
      status
    }
    ... on InvalidInputError {
      message
    }
  }
}
"""


def load_next_item():
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            state = json.load(f)
            idx = state.get("next_index", 0)
    else:
        idx = 0

    if idx >= len(manifest):
        print("No more items in manifest. Add more quotes/posters to keep going.")
        sys.exit(0)

    return manifest[idx], idx


def post_to_buffer(image_url, caption):
    api_key = os.environ.get("MY_BOOK_API_KEY")
    if not api_key:
        raise RuntimeError("MY_BOOK_API_KEY environment variable is not set.")

    variables = {
        "input": {
            "channelId": CHANNEL_ID,
            "schedulingType": "automatic",   # auto-publish, no manual approval
            "mode": "addToQueue",            # goes into Buffer's queue slots
            "text": caption,
            "assets": [
                {"image": {"url": image_url}}
            ],
        }
    }

    resp = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={"query": CREATE_POST_MUTATION, "variables": variables},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data and data["errors"]:
        raise RuntimeError(f"Buffer API returned errors: {data['errors']}")

    result = data["data"]["createPost"]
    if result.get("__typename") == "InvalidInputError":
        raise RuntimeError(f"Invalid input: {result.get('message')}")

    print(f"Posted successfully: {result}")
    return result


def main():
    item, idx = load_next_item()
    post_to_buffer(item["image_url"], item["caption"])

    with open(STATE_PATH, "w") as f:
        json.dump({"next_index": idx + 1}, f)


if __name__ == "__main__":
    main()
