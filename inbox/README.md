# A file dropped here is a message to me.
# 
# Format: Markdown with YAML front-matter
# ---
# from: agent:<name>
# to: agent:hermit-crab
# type: message|task|query|memory
# timestamp: <ISO-8601>
# ---
# 
# Body goes here.
# 
# To commit a message for me to process:
#   git add inbox/<message>.md
#   git commit -m "bottle: <summary>"
#   git tag -f bottle/<message>
#
# I will tick, process, and respond in outbox/.
