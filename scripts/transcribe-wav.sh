#!/usr/bin/env bash
# transcribe-wav.sh — Send a WAV file to Deepgram pre-recorded API and save transcript as .txt
# Usage: ./scripts/transcribe-wav.sh [path/to/file.wav]
# Output: saves transcript alongside the wav as <basename>.txt

set -euo pipefail

WAV="${1:-test_audio/test.wav}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WAV_ABS="$ROOT_DIR/$WAV"
OUT_TXT="${WAV_ABS%.wav}.txt"

# Load .env from project root (strip Windows \r line endings)
ENV_FILE="$ROOT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line; do
    line="${line//$'\r'/}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    export "$line" 2>/dev/null || true
  done < "$ENV_FILE"
fi

if [[ -z "${DEEPGRAM_API_KEY:-}" ]]; then
  echo "ERROR: DEEPGRAM_API_KEY not set. Add it to .env or export it." >&2
  exit 1
fi

if [[ ! -f "$WAV_ABS" ]]; then
  echo "ERROR: File not found: $WAV_ABS" >&2
  exit 1
fi

echo "Transcribing: $WAV_ABS"
echo "Using Deepgram nova-2 model..."

RESPONSE=$(curl -s -X POST \
  "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true&paragraphs=true&diarize=true&utterances=true" \
  -H "Authorization: Token $DEEPGRAM_API_KEY" \
  -H "Content-Type: audio/wav" \
  --data-binary "@$WAV_ABS")

# Extract transcript using python (already available in the project venv)
TRANSCRIPT=$(echo "$RESPONSE" | python3 -c "
import sys, json

try:
    data = json.load(sys.stdin)
except Exception as e:
    print(f'ERROR: Failed to parse response: {e}', file=sys.stderr)
    sys.exit(1)

# Check for API error
if 'err_msg' in data or 'error' in data:
    err = data.get('err_msg') or data.get('error')
    print(f'ERROR: Deepgram API error: {err}', file=sys.stderr)
    sys.exit(1)

# Try paragraphs format first (richest)
try:
    paragraphs = data['results']['channels'][0]['alternatives'][0]['paragraphs']['paragraphs']
    lines = []
    for para in paragraphs:
        speaker = para.get('speaker')
        sentences = ' '.join(s['text'] for s in para.get('sentences', []))
        if speaker is not None:
            lines.append(f'[Speaker {speaker}] {sentences}')
        else:
            lines.append(sentences)
    print('\n\n'.join(lines))
except (KeyError, TypeError):
    # Fallback to plain transcript
    try:
        transcript = data['results']['channels'][0]['alternatives'][0]['transcript']
        print(transcript)
    except (KeyError, TypeError) as e:
        print(f'ERROR: Could not extract transcript: {e}', file=sys.stderr)
        print('Raw response:', json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)
")

echo "$TRANSCRIPT" > "$OUT_TXT"
echo ""
echo "Saved to: $OUT_TXT"
echo ""
echo "--- Transcript preview ---"
head -20 "$OUT_TXT"
