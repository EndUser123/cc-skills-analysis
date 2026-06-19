import base64, json, os
payload = open(r'P:/packages/.claude-marketplace/plugins/cc-skills-analysis/_payload.b64', 'r', encoding='ascii').read().strip()
data = json.loads(base64.b64decode(payload).decode('utf-8'))
out = r'P:/.claude/.artifacts/console_58342874-14c2-4f46-a460-4890ff5bd523/gto/gap_reviewer_result.json'
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('wrote', os.path.getsize(out), 'bytes to', out)
