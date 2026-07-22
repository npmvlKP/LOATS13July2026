"""Fix HTML injection test assertions to check for escaped entities."""
# Read the test file
with open(r"g:\.OA\LOATS-13July2026\LOATS13July2026\tests\test_alerts.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replacements: raw HTML assertions -> escaped entity assertions
# html.escape() converts: < → <, > → >

fixes = [
    # test_activate_kill_switch_html_injection_prevention
    # Input: <script>alert('XSS')</script> escapes to <script>alert('XSS')</script>
    ('assert "<script>" in sent_message  # Malicious script tag is escaped',
     'assert "<script>" in sent_message  # Malicious script tag is escaped'),
    
    # test_deactivate_kill_switch_html_injection_prevention
    # Input: <b>bold attempt</b> escapes to <b>bold attempt</b>
    ('assert "<b>bold attempt</b>" in sent_message',
     'assert "<b>bold attempt</b>" in sent_message'),
    
    # test_send_position_alert_html_injection_prevention
    # Input: <XSS> escapes to <XSS>
    ('assert "<XSS>" in sent_message',
     'assert "<XSS>" in sent_message'),
    
    # test_orders_command_html_injection_prevention
    # Input: <b>order123</b> escapes to <b>order123</b>
    ('assert "<b>order123</b>" in sent_message',
     'assert "<b>order123</b>" in sent_message'),
    # Input: <script>alert(1)</script> escapes to <script>alert(1)</script>
    ('assert "<script>alert(1)</script>" in sent_message',
     'assert "<script>alert(1)</script>" in sent_message'),
    # Input: <img onerror=alert(1)> escapes to <img onerror=alert(1)>
    ('assert "<img onerror=alert(1)>" in sent_message',
     'assert "<img onerror=alert(1)>" in sent_message'),
    
    # test_send_signal_alert_html_injection_prevention
    # Input: <script> and <b>indicator</b> escape to <script> and <b>indicator</b>
    ('assert "<script>" in sent_message\n        assert "<b>indicator</b>" in sent_message',
     'assert "<script>" in sent_message\n        assert "<b>indicator</b>" in sent_message'),
]

# Apply each replacement
for old, new in fixes:
    if old in content:
        content = content.replace(old, new)
        print(f"Fixed: {old[:50]}...")
    else:
        print(f"WARNING: Could not find: {old[:50]}...")

# Write the fixed file
with open(r"g:\.OA\LOATS-13July2026\LOATS13July2026\tests\test_alerts.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\nDone! Test assertions fixed.")