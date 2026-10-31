"""Apply the pinned recipe strictly, refreshing two known overlapping contexts only."""
from pathlib import Path
import subprocess

HEADER = "@@ -607,13 +617,13 @@"
CONTEXT = "         content, calls = parse_tool_calls(raw_answer, tools, max_calls=policy.max_calls) if tools else (answer, None)\n"
REFRESHED = (
    '         rejected: list[str] = []                          # calls to tools the request did not offer: text (#103)\n'
    '         content, calls = (parse_tool_calls(raw_answer, tools, max_calls=policy.max_calls, rejected=rejected) if tools\n'
    '                           else (answer, None))\n'
    '         if rejected:\n'
    '             stats = tool_call_rejections(rejected, len(tools), stats)\n'
)


def refresh_reply_context(text: str) -> str:
    # 0115 introduced diagnostics between raw_answer and policy.content. 0117's
    # context predates that edit. Only context/line counts change; +/- lines do not.
    if text.count(HEADER) != 1 or text.count(CONTEXT) != 1:
        raise ValueError("unexpected 0117 patch; refusing context reconciliation")
    return text.replace(HEADER, "@@ -607,17 +617,17 @@", 1).replace(CONTEXT, REFRESHED, 1)


def refresh_chat_context(text: str) -> str:
    # 0118 inserted exit_on_broken between the two unchanged lines of 0119.
    header = "@@ -562,6 +600,8 @@ class MultiDecoder:"
    old = "         self.idle = True\n         self.broken: Exception | None = None\n"
    new = "         self.idle = True\n         self.exit_on_broken = exit_on_broken()\n         self.broken: Exception | None = None\n"
    if text.count(header) != 1 or text.count(old) != 1:
        raise ValueError("unexpected 0119 patch; refusing context reconciliation")
    return text.replace(header, "@@ -562,7 +600,9 @@ class MultiDecoder:", 1).replace(old, new, 1)


def main() -> None:
    import importlib.util

    root = Path(next(iter(importlib.util.find_spec("tensorfold").submodule_search_locations))).parent
    for path in sorted(Path("/opt/tf-patches").glob("*.patch")):
        text = path.read_text()
        if path.name == "0117-glm-reply-marker-ids.patch":
            text = refresh_reply_context(text)
        elif path.name == "0119-glm-chat-continued.patch":
            text = refresh_chat_context(text)
        print("Strictly applying", path.name, flush=True)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p0", "--forward"],
                       input=text, text=True, cwd=root, check=True)


if __name__ == "__main__":
    main()
