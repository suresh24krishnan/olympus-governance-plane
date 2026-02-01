from olympus.adapters.jira.jira_client import JiraAdapter

jira = JiraAdapter()
# We use the ticket you just created to see what's possible
transitions = jira.client.transitions("SEN-124")

print("--- Available Transitions for SEN-124 ---")
for t in transitions:
    print(f"ID: {t['id']} -> Name: {t['name']}")