import os
import sys

# Add campaign_app/ to path so tests import the same way pages do
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "campaign_app"))
