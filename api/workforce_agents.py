"""Approved AI roles. Adding a role never grants a new business-system tool."""
import re

EMPLOYEES = [
    {'id': 'ai-manager', 'name': 'Archet AI Manager', 'handle': 'manager', 'department': 'Management', 'initials': 'AM',
     'description': 'Plans work, helps with writing and code, and adds specialist AI teammates.'},
    {'id': 'ai-operations', 'name': 'Operations Agent', 'handle': 'operations', 'department': 'Operations', 'initials': 'OP',
     'description': 'Reads saved sales reports and explains store performance.'},
]
SPECIALISTS = [
    {'id': 'ai-hr', 'name': 'HR Agent', 'handle': 'hr', 'department': 'HR', 'initials': 'HR',
     'description': 'Drafts onboarding plans, policies, feedback and employee communications.'},
    {'id': 'ai-finance', 'name': 'Finance Agent', 'handle': 'finance', 'department': 'Finance', 'initials': 'FI',
     'description': 'Helps with budgets, financial explanations and analysis of figures shared in chat.'},
    {'id': 'ai-engineering', 'name': 'Engineering Agent', 'handle': 'engineering', 'department': 'Engineering', 'initials': 'EN',
     'description': 'Writes and reviews code, explains technical issues and plans implementations.'},
    {'id': 'ai-marketing', 'name': 'Marketing Agent', 'handle': 'marketing', 'department': 'Marketing', 'initials': 'MK',
     'description': 'Drafts campaigns, content, product messaging and marketing plans.'},
    {'id': 'ai-recruiting', 'name': 'Recruiting Agent', 'handle': 'recruiting', 'department': 'Recruiting', 'initials': 'RE',
     'description': 'Drafts job descriptions, interview questions and hiring workflows.'},
    {'id': 'ai-support', 'name': 'Support Agent', 'handle': 'support', 'department': 'Customer support', 'initials': 'CS',
     'description': 'Drafts customer replies, troubleshooting guides and support procedures.'},
]
AGENTS = {agent['id']: agent for agent in [*EMPLOYEES, *SPECIALISTS]}
DEFAULT_IDS = [agent['id'] for agent in EMPLOYEES]


def mentioned_people(content, participants):
    # Stable handles avoid ambiguity from duplicate display names. Email
    # addresses and partial handles do not create mentions.
    content = re.sub(r'```[\s\S]*?```|`[^`\n]*`', '', content)
    handles = {m.lower() for m in re.findall(r'(?<![\w@])@([A-Za-z0-9_-]+)(?![\w-])', content)}
    return [person for person in participants if person['handle'].lower() in handles]
