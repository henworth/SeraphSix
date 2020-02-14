from functools import reduce
from seraphsix.cogs.utils.helpers import merge_dicts, sort_dict
from seraphsix.constants import THE100_GAME_SORT_RULES


def collate_the100_activities(activities, game_name):
    # Build a list and a dictionary (keyed by id) of all activities
    game_activities = []
    game_activities_by_id = {}
    for activity in activities:
        key = activity['name'].strip()
        val = activity['id']
        game_activities_by_id[val] = key

        # Sanitize the game names to ensure merging works correctly, raids require 'Fresh' to be appended,
        # other things require 'Normal', and one requires 'Anything'
        if key in THE100_GAME_SORT_RULES[game_name]['fresh']:
            key = f"{key} - Fresh"
        elif key in THE100_GAME_SORT_RULES[game_name]['normal']:
            key = f"{key} - Normal"
        elif key in THE100_GAME_SORT_RULES[game_name]['anything']:
            key = f"{key} - Anything"
        game_activities.append({key: val})

    # Create a list of nested dictionaries created by splitting the name by ' - ', ie.
    #
    # If the output of the previous loop is this:
    # [{'Raid - Crown of Sorrow - Fresh': 1}, {'Raid - Last Wish - Fresh': 2}]
    #
    # It turns into:
    # [{'Raid': {'Crown of Sorrow': {'Fresh': 1}}}, {'Raid': {'Last Wish': {'Fresh': 2}}}]
    game_activities_list = []
    for game_activity in game_activities:
        game_activities_list.append(reduce(lambda res, cur: {cur: res}, reversed(
            list(game_activity.keys())[0].split(' - ')), list(game_activity.values())[0]))

    # Merge the list of dictionaries into one big dictionary
    # {'Raid': {'Crown of Sorrow': {'Fresh': 1}}, {'Last Wish': {'Fresh': 2}}}
    game_activities_dict = (reduce(merge_dicts, game_activities_list))

    # Sort the contents of the above into a new dict
    game_activities_merged = {}
    for key in ['Raid', 'Crucible', 'Gambit', 'Strike', 'Quest']:
        unsorted = game_activities_dict.pop(key)
        try:
            game_activities_merged[key] = sort_dict(unsorted)
        except AttributeError:
            game_activities_merged[key] = unsorted

    # Anything left over in that dict is added under a single category
    game_activities_merged['Other'] = sort_dict(game_activities_dict)

    return game_activities_merged, game_activities_by_id
