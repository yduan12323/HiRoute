"""Milestone 4A: structured opportunities and user-agnostic route-attached regions."""
from .models import (OpportunityId, Opportunity, Provenance, DecisionOpportunity,
                     OpportunityRegion, ODContext, decision_features, eligible_opportunities)
from .attachment import attach_opportunities
from .regions import OpportunityRegionBuilder, GeographicRegionBuilder, DecisionRegionBuilder
