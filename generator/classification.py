"""Which data from another age may be loaded into the running game.

Design rule (design doc, "Content per civ, systems per world"):
  * Content is what a civ researches, builds or uses. It is loaded from every
    age and locked per civ by that civ's breakthrough tech.
  * Systems are data that switch engine behaviour on, or that an age transition
    sets up (treasure fleets, independent powers, narratives, legacy cards,
    victories, AI, global parameters). They stay with their own age and start
    when the world age reaches that age.

The content list is an allow list. A table that is on neither list (for example
one that a game patch or DLC adds) is not loaded and is reported as
unclassified, so a new mechanic is missing until reviewed, never active in the
wrong age.
"""
import fnmatch

CONTENT_TABLES = {
    # Tech and civic trees
    "ProgressionTrees", "ProgressionTreeNodes", "ProgressionTreePrereqs", "ProgressionTreeNodeUnlocks",
    "ProgressionTreeNodeTraits", "ProgressionTree_Advisories", "RequirementStrings",
    # Units
    "Units", "Unit_Stats", "Unit_Costs", "Unit_Advisories", "Unit_RequiredConstructibles", "UnitUpgrades",
    "UnitReplaces", "UnitAbilities", "UnitAbilityModifiers", "UnitClass_Abilities", "Unit_ShadowReplacements",
    "AIUnitPrioritizedActions", "ChargedUnitAbilities", "WMDs",
    # Buildings, improvements, wonders, quarters
    "Constructibles", "Buildings", "Improvements", "Wonders", "UniqueQuarters", "UniqueQuarterModifiers",
    "ConstructibleModifiers", "Adjacency_YieldChanges", "Warehouse_YieldChanges", "District_FreeConstructibles",
    "Constructible_Adjacencies", "Constructible_Advisories", "Constructible_BuildingCostProgressions",
    "Constructible_FreeRoads", "Constructible_GreatWorks", "Constructible_InvalidAdjacentBiomes",
    "Constructible_Logistics", "Constructible_Maintenances", "Constructible_Plunders",
    "Constructible_RequiredFeatureClasses", "Constructible_ValidBiomes", "Constructible_ValidDistricts",
    "Constructible_ValidTerrains", "Constructible_WarehouseYields", "Constructible_WildcardAdjacencies",
    "Constructible_YieldChanges", "Constructible_PillageRandomEvents", "Routes",
    # Civs of the age (their abilities and unique items)
    "Traits", "TraitModifiers", "StartBiasResources", "NamedRiverCivilizations", "NamedVolcanoCivilizations",
    "NarrativeDisplay_Civilizations",
    # Governments and celebrations
    "Governments", "GovernmentModifiers", "GovernmentAttributes", "Government_ValidGoldenAges",
    "StartingGovernments", "GoldenAges", "GoldenAgeModifiers", "TraditionModifiers",
    # Ideologies: chosen through Modern civics, so they arrive with the civ's civic tree
    "Ideologies", "IdeologyAdoptionModifiers",
    # Great people, great works, projects
    "GreatPersonClasses", "GreatPersonIndividuals", "GreatPersonIndividualActionModifiers",
    "GreatWorks", "GreatWork_YieldChanges", "GreatWork_ValidSubTypes", "GreatWorkObjectTypes",
    "GreatWorkSlotTypes", "GreatWorkSourceTypes", "Projects", "ProjectModifiers", "ProjectCompletionModifiers", "Project_YieldConversions",
    # Resources (their classes are systems: see SYSTEM_TABLES)
    "Resources", "TradeYields", "ModifierMetadatas", "PlayerInventoryItems",
    # Shared definitions; inert until a content or system table attaches them
    "Types", "Tags", "TypeTags", "TypeQuotes", "Modifiers", "ModifierArguments", "ModifierStrings",
    "Requirements", "RequirementArguments", "RequirementSets", "RequirementSetRequirements",
    "GameModifiers",
}

# Generic tables that attach modifiers to the whole game or to traits. They are
# content only when they come from content files.
CONTENT_TABLE_FILES = {
    "GameModifiers": ["constructible*.xml"],          # unique quarter effects
    "TraitModifiers": ["civilizations-*.xml"],        # civ abilities (not difficulty traits)
}

# Type kinds that are content. Types of other kinds belong to systems.
CONTENT_KINDS = {
    "KIND_TREE", "KIND_TREE_NODE", "KIND_UNIT", "KIND_ABILITY", "KIND_CONSTRUCTIBLE", "KIND_QUARTER",
    "KIND_GOVERNMENT", "KIND_GOLDEN_AGE", "KIND_PROJECT", "KIND_GREATWORK", "KIND_GREAT_PERSON_INDIVIDUAL",
    "KIND_GREAT_PERSON_CLASS", "KIND_RESOURCE", "KIND_TRAIT", "KIND_MODIFIER", "KIND_TAG",
    "KIND_ROUTE", "KIND_WMD", "KIND_GREATWORKSOURCE", "KIND_GREATWORKOBJECT", "KIND_IDEOLOGY",
}

# Tables known to be systems. Listed so that a new table stands out as unclassified.
SYSTEM_TABLES = {
    # Age progression, legacy paths, victories, legacy cards
    "AgeProgressions", "AgeProgressionEvents", "AgeProgressionEventMapSizeOverrides", "AgeProgressionTurns",
    "AgeProgressionMilestones", "AgeProgressionMilestoneRewards", "AgeProgressionDarkAgeRewardInfos",
    "Legacies", "LegacyModifiers", "Legacy_LegacySets", "PlayerModifiers", "Strategy_Legacies",
    # Age balance values (one global value per age)
    "AgeConstructibleDefaultMaintenances", "AgeConstructibleDefaultYields", "AgeGrowthBalances",
    "WorkerYields", "WorkerYields_AgeModifier", "TerrainBiomeFeature_YieldChanges", "HappinessStages",
    "WarWearinessEffects", "GlobalParameters", "UnitMovementClassObstacles", "Unit_TransitionRetains",
    # Engine systems switched on by data
    "GameSystemPrereqs", "GameCapabilities", "GameCapabilityDependencies", "ResourceClasses",
    "ResourceClassApplicableLegacyPaths", "Pseudoyields", "PseudoYields", "Kinds",
    # Independent powers and city-state bonuses
    "Independents", "LegacyIndependents", "CityStateBonuses", "CityStateBonusModifiers", "Affinities",
    "TribeTagSets", "VisArt_IndependentBuildingCultures", "VisArt_IndependentUnitCultures",
    # Diplomacy
    "DiplomacyActions", "DiplomaticActionStages", "DiplomaticActionValidTokens", "DiplomaticActionResponses",
    "DiplomaticActionResponseModifiers", "DiplomaticActionInfluenceCosts", "DiplomaticProjects_UI_Data",
    "DiplomacyFavorsGrievancesEventsData", "EnterStageModifiers", "DealItemGold", "DealItemInfluence",
    # Narratives and discoveries
    "NarrativeStories", "NarrativeStory_Links", "NarrativeStory_Rewards", "NarrativeStory_TextReplacements",
    "NarrativeStory_Yield_Rewards", "NarrativeStory_Queues", "NarrativeStoryOverrides", "NarrativeRewards",
    "NarrativeRewardIcons", "NarrativeVariations", "DiscoveryStory_Yield_Rewards",
    # Religion (founding and spread)
    "Beliefs", "BeliefClasses", "BeliefModifiers", "Belief_Priorities",
    # AI behaviour per age
    "AiComponents", "AiDefinitions", "AiFavoredItems", "AiListTypes", "AiLists", "AiOperationDefs",
    "AiOperationTeams", "AiOperationTypes", "AiTactics", "AiTeams", "AllowedOperations", "OpTeamRequirements",
    "Strategies", "StrategyConditions", "Strategy_Priorities", "TargetTypes",
    # Difficulty, civ unlocks for the next age, Civilopedia
    "StandardHandicaps", "HandicapSystems", "UnlockRequirements", "UnlockRewards", "UnlockConfigurationValues",
    "CivilopediaPageExcludes",
    # Age start and transition setup (advanced start decks, legacy points, armies kept)
    "AdvancedStartArmyUnits", "AdvancedStartBuildings", "AdvancedStartCardEffects", "AdvancedStartCardSets",
    "AdvancedStartCards", "AdvancedStartDeckCardEntries", "AdvancedStartDecks", "AdvancedStartParameters",
    "AdvancedStartTowns", "AdvancedStartUnits", "AllowedFreeUnits", "Maps", "AgeTransitionArmyUnits",
    "AgeTransitionBoostableNodes", "AgeTransitionCardSets", "AgeTransitionLegacyPoints", "AgeTransitionParameters",
    "AgeTransitionRespawnModifiers", "AgeTransitionRespawnParameters", "AgeTransitionRespawnUnits", "Ages",
    "AgeProgressionRewards", "GreatPersonVictoryTypeEntries",
    # Crises (one global world meter), goody huts, map generation
    "AgeCrises", "AgeCrisisEvents", "AgeCrisisStages", "GoodyHuts", "GoodyHutSubTypes", "Resource_ValidBiomes",
    "Resource_RequiredCivs",
    # More AI, diplomacy, presentation
    "AIListTypes", "AILists", "AiUnitEfficiencyBonuses", "IdeologyPriorities", "DiplomacyBonusEnvoyData",
    "AdvisorWarnings", "Movies", "EndGameMovies", "MetaprogressionModifiers",
}


def table_class(table: str, file_name: str) -> str:
    """'content', 'system' or 'unclassified' for a table in a given source file."""
    if table in CONTENT_TABLES:
        patterns = CONTENT_TABLE_FILES.get(table)
        if patterns is None or any(fnmatch.fnmatch(file_name, p) for p in patterns):
            return "content"
        return "system"
    if table in SYSTEM_TABLES:
        return "system"
    return "unclassified"


def type_is_content(kind: str | None) -> bool:
    return kind in CONTENT_KINDS
