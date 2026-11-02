// Continuous Ages: helpers for live tests (generator/live.py), in test builds only (build_mod.py --checks).
// globalThis.caLive is used by scenario scripts that live.py runs in the game's UI context. Two ways in:
//   - the automation test "CALive" (checks/ca-automation.js imports this file): a game that a suite sets up;
//   - a normal game that live.py hosts from the main menu (live.py start --manual): live.py injects this file's
//     text after each page load, so the human's own screens (the age-end and civ selection screens) run as in
//     a player's game. The automation test cannot do that: it chooses the human's civ at a transition at random.
// No imports, and safe to run twice (the second run does nothing).
(() => {
  if (globalThis.caLive?.version === 1) return;
  const log = (record) => console.warn(`[CA-CHECK][SCENARIO] ${JSON.stringify(record)}`);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const localId = () => GameContext.localPlayerID;
  const capitalOf = (pid) => (Players.get(pid)?.Cities?.getCityIds() ?? []).find((id) => Cities.get(id)?.isCapital);
  // A node counts as done at depth 1 (the same rule as nodeDone in ca-checks.js).
  const nodeDone = (pid, hash) => {
    const S = ProgressionTreeNodeState;
    const s = Game.ProgressionTrees.getNodeState(pid, hash);
    if (s >= S.NODE_STATE_FULLY_UNLOCKED || s === S.NODE_STATE_UNLOCKED) return true;
    return s === S.NODE_STATE_IN_PROGRESS && (Game.ProgressionTrees.getNode(pid, hash)?.depthUnlocked ?? 0) >= 1;
  };
  function onceEvent(name, test = () => true, timeoutMs = 600000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { engine.off(name, listener); reject(new Error(`timed out waiting for ${name}`)); }, timeoutMs);
      const listener = (data) => {
        if (!test(data)) return;
        clearTimeout(timer);
        engine.off(name, listener);
        resolve(data);
      };
      engine.on(name, listener);
    });
  }
  const caLive = {
    version: 1,
    ready: false,
    ageEnded: false,
    log,
    sleep,
    hasNode(type, pid = localId()) {
      const hash = GameInfo.ProgressionTreeNodes.lookup(type)?.$hash;
      return hash !== undefined && nodeDone(pid, hash);
    },
    // The AI plays slot 0 for about n turns (Autoplay), then gives it back. Autoplay's turn count is not exact
    // (live test: 1 turn from turn 1 played none, 2 from turn 1 reached turn 3, and the turn can move once more
    // after it ends), so this resolves when slot 0's turn is active and the turn has stayed the same for 2 s.
    async advance(n = 1) {
      const done = onceEvent("AutoplayEnded");
      Autoplay.setTurns(n);
      Autoplay.setReturnAsPlayer(0);
      Autoplay.setObserveAsPlayer(0);
      Autoplay.setActive(true);
      await done;
      let turn = -1;
      for (let i = 0; i < 120; i++) {
        await sleep(1000);
        const active = Players.get(localId())?.isTurnActive && !Autoplay.isActive;
        if (active && Game.turn === turn) break;
        turn = active ? Game.turn : -1;
      }
      return Game.turn;
    },
    // Ends slot 0's turn without the AI (it works with open turn blockers). Right after autoplay the game can ignore
    // the request (live test: the turn stayed the same), so it is sent again while the turn has not ended. Resolves
    // at the next turn, or when the age ends (then no new turn begins).
    async endTurn(timeoutMs = 120000) {
      const turn = Game.turn;
      const t0 = Date.now();
      let lastSend = 0;
      while (Date.now() - t0 < timeoutMs) {
        if (Game.turn > turn || caLive.ageEnded) return Game.turn;
        if (Players.get(localId())?.isTurnActive && Date.now() - lastSend > 4000) {
          GameContext.sendTurnComplete();
          lastSend = Date.now();
        }
        await sleep(500);
      }
      throw new Error(`endTurn: turn ${turn} did not end in ${timeoutMs / 1000} s`);
    },
    // The age's end as a human reaches it, in a build with short ages (build_mod.py --age-points N): the AI plays
    // slot 0 until the age is 3 points from its end, then slot 0 ends its own turns until the age ends. Autoplay
    // must not run into the age end: in an automation test the game then makes the transition itself, with a random
    // civ for slot 0. Not Game.AgeProgressManager.updateAgeProgressionPoints (a tuner panel call): from the UI it
    // crashed the game in the age-end code (EndAgeNextTurn, AgeOver; 2026-10-31).
    async toAgeEnd(maxTurns = 30) {
      const m = Game.AgeProgressManager;
      const left = () => m.getMaxAgeProgressionPoints() - m.getCurrentAgeProgressionPoints();
      for (let i = 0; i < maxTurns && left() > 3 && !caLive.ageEnded; i++) await caLive.advance(1);
      for (let i = 0; i < 8 && !caLive.ageEnded; i++) await caLive.endTurn();
      return { ageEnded: caLive.ageEnded, turn: Game.turn, points: m.getCurrentAgeProgressionPoints(), max: m.getMaxAgeProgressionPoints() };
    },
    // The engine's answers for training a unit in slot 0's capital (the UI's queries are reliable for slot 0).
    canTrain(unitType, pid = localId()) {
      const city = capitalOf(pid);
      const def = GameInfo.Units.lookup(unitType);
      if (city === undefined || !def) return { city: city !== undefined, unit: !!def };
      const r = Game.CityOperations.canStart(city, CityOperationTypes.BUILD, { UnitType: def.$hash }, false);
      const q = (Game.CityOperations.canStartQuery(city, CityOperationTypes.BUILD, CityQueryType.Unit) ?? []).find((x) => x.index === def.$index)?.result;
      return { ok: !!r?.Success, reasons: r?.FailureReasons ?? [], listed: !!q, queryOk: !!q?.Success, neededUnlock: q?.NeededUnlock,
               buildUnit: GameInfo.Units.lookup(Players.get(pid)?.Units?.getBuildUnit(unitType))?.UnitType ?? null };
    },
    // Debug operations (the game's tuner panels use them); canStart first, so a refusal shows its reasons. The game
    // handles a request a moment later.
    grantNode(type, pid = localId(), fullyUnlock = 0) {
      const args = { ProgressionTreeNodeType: GameInfo.ProgressionTreeNodes.lookup(type)?.$hash, FullyUnlock: fullyUnlock };
      const can = Game.PlayerOperations.canStart(pid, PlayerOperationTypes.GRANT_TREE_NODE, args, false);
      if (can?.Success) Game.PlayerOperations.sendRequest(pid, PlayerOperationTypes.GRANT_TREE_NODE, args);
      return { sent: !!can?.Success, reasons: can?.FailureReasons ?? [] };
    },
    async grantNodeAndWait(type, pid = localId()) {
      caLive.grantNode(type, pid);
      for (let i = 0; i < 10 && !caLive.hasNode(type, pid); i++) await sleep(500);
      return caLive.hasNode(type, pid);
    },
    // CREATE_ELEMENT places a unit only on a plot the player has revealed, and moves it to the nearest valid plot.
    createUnit(type, x, y, pid = localId()) {
      const args = { Kind: "UNIT", Type: type, Location: { x, y }, Owner: pid };
      const can = Game.PlayerOperations.canStart(pid, "CREATE_ELEMENT", args, false);
      Game.PlayerOperations.sendRequest(pid, "CREATE_ELEMENT", args);
      return { canStart: !!can?.Success, reasons: can?.FailureReasons ?? [] };
    },
    // Polls test() every 500 ms until it returns a true value or timeoutMs has passed, and returns its last value.
    // For a request that the game handles a moment later: with several games at once, a fixed wait can end too soon.
    async waitFor(test, timeoutMs = 15000) {
      const t0 = Date.now();
      let value = test();
      while (!value && Date.now() - t0 < timeoutMs) {
        await sleep(500);
        value = test();
      }
      return value;
    },
    // createUnit, then wait (up to timeoutMs) for the new unit of that type. Returns the unit, or null. In regression
    // 20261101-191259 (6 games at once) a ship came more than 2 s after the request (meet_distant.js). A unit id is
    // keyed as the base game's ComponentID.toString does (owner;id;type).
    async createUnitAndWait(type, x, y, pid = localId(), timeoutMs = 15000) {
      const key = (id) => `${id?.owner};${id?.id};${id?.type}`;
      const ids = () => Players.get(pid)?.Units?.getUnitIds() ?? [];
      const old = new Set(ids().map(key));
      caLive.createUnit(type, x, y, pid);
      const fresh = () => ids().filter((id) => !old.has(key(id))).map((id) => Units.get(id))
        .find((u) => u && GameInfo.Units.lookup(u.type)?.UnitType === type) ?? null;
      return await caLive.waitFor(fresh, timeoutMs);
    },
    // A world transition as the human starts it (the legends screen's button) after the age has ended. In a normal
    // game (live.py start --manual) the game then shows the shell's civ selection screen, where live.py makes slot
    // 0's choice; in an automation test the game has already made the transition itself.
    transition() {
      globalThis.caTransitionCivs?.("live");
      log({ transition: true, turn: Game.turn, age: GameInfo.Ages.lookup(Game.age)?.AgeType, ageEnded: caLive.ageEnded });
      setTimeout(() => engine.call("transitionToNextAge"), 1500);  // later: the phase's result first reaches live.py
      return true;
    },
  };
  engine.on("GameAgeEnded", () => { caLive.ageEnded = true; log({ ageEnded: true, turn: Game.turn }); });
  globalThis.caLive = caLive;
})();
