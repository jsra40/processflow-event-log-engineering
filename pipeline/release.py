
from __future__ import annotations
import json, platform, sys
from datetime import datetime, timezone

PIPELINE_VERSION="1.4.2"

def release_metadata():
    return {
      "pipeline_version":PIPELINE_VERSION,
      "generated_at_utc":datetime.now(timezone.utc).isoformat(),
      "python_version":sys.version.split()[0],
      "platform":platform.platform(),
    }
