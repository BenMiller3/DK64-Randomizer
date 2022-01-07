"""Module used to distribute items randomly."""
import copy
import random

import randomizer.Exceptions as Ex
import randomizer.ItemPool as ItemPool
import randomizer.Logic as Logic
import randomizer.Exceptions as Ex
from randomizer.Location import LocationList
from randomizer.Item import ItemList
from randomizer.Logic import LogicVarHolder, LogicVariables

from randomizer.Enums.Items import Items
from randomizer.Enums.Regions import Regions
from randomizer.Enums.SearchMode import SearchMode
from randomizer.ShuffleExits import ShufflableExits, ExitShuffle


def GetAccessibleLocations(ownedItems, searchType=SearchMode.GetReachable):
    """Search to find all reachable locations given owned items."""
    accessible = []
    newLocations = []
    playthroughLocations = []
    eventAdded = True
    # Continue doing searches until nothing new is found
    while len(newLocations) > 0 or eventAdded:
        # Add items and events from the last search iteration
        sphere = []
        for locationId in newLocations:
            accessible.append(locationId)
            location = LocationList[locationId]
            # If this location has an item placed, add it to owned items
            if location.item is not None:
                ownedItems.append(location.item)
            # If we want to generate the playthrough and the item is a playthrough item, add it to the sphere
            if searchType == SearchMode.GeneratePlaythrough and ItemList[location.item].playthrough:
                # Banana hoard in a sphere by itself
                if location.item == Items.BananaHoard:
                    sphere = [locationId]
                    break
                sphere.append(locationId)
            # If we're checking beatability, just want to know if we have access to the banana hoard
            if searchType == SearchMode.CheckBeatable and location.item == Items.BananaHoard:
                return True
        if len(sphere) > 0:
            playthroughLocations.append(sphere)
            if LocationList[sphere[0]].item == Items.BananaHoard:
                break
        eventAdded = False
        # Reset new lists
        newLocations = []
        # Update based on new items
        LogicVariables.Update(ownedItems)

        # Do a search for each owned kong
        for kong in LogicVariables.GetKongs():
            LogicVariables.SetKong(kong)

            startRegion = Logic.Regions[Regions.Start]
            startRegion.id = Regions.Start
            regionPool = [startRegion]
            addedRegions = [Regions.Start]

            tagAccess = [
                (key, value)
                for (key, value) in Logic.Regions.items()
                if value.HasAccess(kong) and key not in addedRegions
            ]
            addedRegions.extend([x[0] for x in tagAccess])  # first value is the region key
            regionPool.extend([x[1] for x in tagAccess])  # second value is the region itself

            # Loop for each region until no more accessible regions found
            while len(regionPool) > 0:
                region = regionPool.pop()
                region.UpdateAccess(kong, LogicVariables)  # Set that this kong has access to this region
                LogicVariables.UpdateCurrentRegionAccess(region)  # Set in logic as well

                # Check accessibility for each location in this region
                for location in region.locations:
                    if (
                        location.logic(LogicVariables)
                        and location.id not in newLocations
                        and location.id not in accessible
                    ):
                        newLocations.append(location.id)
                # Check accessibility for each event in this region
                for event in region.events:
                    if event.name not in LogicVariables.Events and event.logic(LogicVariables):
                        eventAdded = True
                        LogicVariables.Events.append(event.name)
                # Check accessibility for each exit in this region
                for exit in region.exits:
                    destination = exit.dest
                    # If this exit has an entrance shuffle id and the shufflable exits list has it marked as shuffled,
                    # use the entrance it was shuffled to by getting the region of the destination exit.
                    if exit.entranceShuffleId is not None:
                        shuffledExit = ShufflableExits[exit.entranceShuffleId]
                        if shuffledExit.shuffled:
                            destination = ShufflableExits[shuffledExit.dest].region
                    # If a region is accessible through this exit and has not yet been added, add it to the queue to be visited eventually
                    if destination not in addedRegions and exit.logic(LogicVariables):
                        addedRegions.append(destination)
                        newRegion = Logic.Regions[destination]
                        newRegion.id = destination
                        regionPool.append(newRegion)
                # Finally check accessibility for collectibles
                if region.id in Logic.CollectibleRegions.keys():
                    for collectible in Logic.CollectibleRegions[region.id]:
                        if not collectible.added and kong == collectible.kong and collectible.logic(LogicVariables):
                            LogicVariables.AddCollectible(collectible, region.level)

    if searchType == SearchMode.GetReachable:
        return accessible
    elif searchType == SearchMode.CheckBeatable:
        # If the search has completed and banana hoard has not been found, game is unbeatable
        return False
    elif searchType == SearchMode.GeneratePlaythrough:
        return playthroughLocations


def RandomFill(itemsToPlace):
    """Randomly place given items in any location disregarding logic."""
    random.shuffle(itemsToPlace)
    # Get all remaining empty locations
    empty = []
    for (id, location) in LocationList.items():
        if location.item is None:
            empty.append(id)
    random.shuffle(empty)
    # Place item in random locations
    while len(itemsToPlace) > 0:
        if len(empty) == 0:
            return len(itemsToPlace)
        item = itemsToPlace.pop()
        locationId = empty.pop()
        LocationList[locationId].PlaceItem(item)
    return 0


def Reset():
    """Reset logic variables and region info that should be reset before a search."""
    LogicVariables.Reset()
    Logic.ResetRegionAccess()
    Logic.ResetCollectibleRegions()


def ParePlaythrough(PlaythroughLocations):
    """Pares playthrough down to only the essential elements."""
    locationsToAddBack = []
    # Check every location in the list of spheres.
    for i in range(len(PlaythroughLocations) - 2, -1, -1):
        sphere = PlaythroughLocations[i]
        for locationId in sphere.copy():
            location = LocationList[locationId]
            # Copy out item from location
            item = location.item
            location.item = None
            # Check if the game is still beatable
            Reset()
            if GetAccessibleLocations([], SearchMode.CheckBeatable):
                # If the game is still beatable, this is an unnecessary location, remove it.
                sphere.remove(locationId)
                # We delay the item to ensure future locations which may rely on this one
                # do not give a false positive for beatability.
                location.SetDelayedItem(item)
                locationsToAddBack.append(locationId)
            else:
                # Else it is essential, don't remove it from the playthrough and add the item back.
                location.PlaceItem(item)

    # Check if there are any empty spheres, if so remove them
    for i in range(len(PlaythroughLocations) - 2, -1, -1):
        sphere = PlaythroughLocations[i]
        if len(sphere) == 0:
            PlaythroughLocations.remove(sphere)

    # Re-place those items which were delayed earlier.
    for locationId in locationsToAddBack:
        LocationList[locationId].PlaceDelayedItem()


def ForwardFill(itemsToPlace, ownedItems=[]):
    """Forward fill algorithm for item placement."""
    random.shuffle(itemsToPlace)
    ownedItems = ownedItems.copy()
    # While there are items to place
    while len(itemsToPlace) > 0:
        # Find a random empty location which is reachable with current items
        reachable = GetAccessibleLocations(ownedItems.copy())
        reachable = [x for x in reachable if LocationList[x].item is None]
        if len(reachable) == 0:  # If there are no empty reachable locations, reached a dead end
            return len(itemsToPlace)
        random.shuffle(reachable)
        locationId = reachable.pop()
        # Get a random item and place it there, also adding to owned items
        item = itemsToPlace.pop()
        ownedItems.append(item)
        LocationList[locationId].PlaceItem(item)
    return 0


def AssumedFill(itemsToPlace, ownedItems=[]):
    """Assumed fill algorithm for item placement."""
    random.shuffle(itemsToPlace)
    # While there are items to place
    while len(itemsToPlace) > 0:
        # Get a random item, check which empty locations are still accessible without owning it
        item = itemsToPlace.pop()
        ownedItems = itemsToPlace.copy()
        ownedItems.extend(ownedItems)
        Reset()
        reachable = GetAccessibleLocations(ownedItems.copy())
        reachable = [x for x in reachable if LocationList[x].item is None]
        # If there are no empty reachable locations, reached a dead end
        if len(reachable) == 0:
            return len(itemsToPlace)
        # Get a random, empty, reachable location and place the item there
        random.shuffle(reachable)
        locationId = reachable.pop()
        LocationList[locationId].PlaceItem(item)
    return 0


def PlaceItems(algorithm, itemsToPlace, ownedItems=[]):
    """Places items using given algorithm."""
    if algorithm == "assumed":
        return AssumedFill(itemsToPlace, ownedItems)
    elif algorithm == "forward":
        return ForwardFill(itemsToPlace, ownedItems)


def Fill(spoiler):
    """Place all items."""
    retries = 0
    algorithm = spoiler.settings.Algorithm
    while True:
        try:
            # First place constant items
            ItemPool.PlaceConstants(spoiler.settings)
            # Then place priority (logically very important) items
            highPriorityUnplaced = PlaceItems(
                algorithm, ItemPool.HighPriorityItems(spoiler.settings), ItemPool.HighPriorityAssumedItems(spoiler.settings)
            )
            if highPriorityUnplaced > 0:
                raise Ex.ItemPlacementException(str(highPriorityUnplaced) + " unplaced high priority items.")
            # Then place blueprints
            Reset()
            blueprintsUnplaced = PlaceItems(algorithm, ItemPool.Blueprints(spoiler.settings), ItemPool.BlueprintAssumedItems(spoiler.settings))
            if blueprintsUnplaced > 0:
                raise Ex.ItemPlacementException(str(blueprintsUnplaced) + " unplaced blueprints.")
            # Then place the rest of items
            Reset()
            lowPriorityUnplaced = PlaceItems(algorithm, ItemPool.LowPriorityItems(spoiler.settings), ItemPool.ExcessItems(spoiler.settings))
            if lowPriorityUnplaced > 0:
                raise Ex.ItemPlacementException(str(lowPriorityUnplaced) + " unplaced low priority items.")
            # Finally place excess items fully randomly
            excessUnplaced = RandomFill(ItemPool.ExcessItems(spoiler.settings))
            if excessUnplaced > 0:
                raise Ex.ItemPlacementException(str(excessUnplaced) + " unplaced excess items.")
            # Check if game is beatable
            Reset()
            if not GetAccessibleLocations([], SearchMode.CheckBeatable):
                raise Ex.GameNotBeatableException("Game unbeatable after placing all items.")
            # Generate and display the playthrough
            Reset()
            PlaythroughLocations = GetAccessibleLocations([], SearchMode.GeneratePlaythrough)
            ParePlaythrough(PlaythroughLocations)
            # Write data to spoiler and return
            spoiler.UpdateLocations(LocationList)
            spoiler.UpdatePlaythrough(LocationList, PlaythroughLocations)
            return spoiler
        except Ex.FillException as ex:
            if retries == 4:
                print("Fill failed, out of retries.")
                raise ex
            else:
                retries += 1
                print("Fill failed. Retrying. Tries: " + str(retries))
                Reset()
                Logic.ClearAllLocations()

def Generate(spoiler):
    """Generate a complete spoiler based on input settings."""
    # Init logic vars with settings
    global LogicVariables
    LogicVariables = LogicVarHolder(spoiler.settings)
    # Handle ER
    if spoiler.settings.ShuffleLevels or spoiler.settings.ShuffleLoadingZones:
        ExitShuffle(spoiler.settings)
        Reset()
    # Place items
    if spoiler.settings.ShuffleItems:
        Fill(spoiler)
    else:
        # Just check if normal item locations are beatable with given settings
        for location in LocationList:
            LocationList[location].PlaceDefaultItem()
        ItemPool.PlaceConstants(spoiler.settings)
        if not GetAccessibleLocations([], SearchMode.CheckBeatable):
            raise Ex.VanillaItemsGameNotBeatableException("Game unbeatable.")
        # Playthrough and location list probably unnecessary with vanilla items
        # Reset()
        # PlaythroughLocations = GetAccessibleLocations([], SearchMode.GeneratePlaythrough)
        # ParePlaythrough(PlaythroughLocations)
        # # Write data to spoiler and return
        # spoiler.UpdateLocations(LocationList)
        # spoiler.UpdatePlaythrough(LocationList, PlaythroughLocations)
    return spoiler
