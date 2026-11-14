"""PIVOT v2 rules and server-authoritative game actions."""
from copy import deepcopy

SIZE = 7

def new_game(player_names=None):
    names = player_names or {"R": "Joueur 1", "B": "Joueur 2"}
    board = [[None for _ in range(SIZE)] for _ in range(SIZE)]
    board[3][3] = {"type": "trace", "cote": None}
    return {
        "cases": board, "pivot": {"x": 3, "y": 3}, "traits": [], "tour": "R",
        "stock": {c: {"bornes": 3, "virage": 2, "tp": 1, "diagonale": 1} for c in ("R", "B")},
        "noms": names, "coups": 0, "attenteEchange": False, "enTp": False,
        "gagnant": None,
    }

def _inside(x, y): return isinstance(x, int) and isinstance(y, int) and 0 <= x < SIZE and 0 <= y < SIZE
def _other(side): return "B" if side == "R" else "R"
def _axis(side): return "H" if side == "R" else "V"
def _destinations(game, axis):
    x, y = game["pivot"]["x"], game["pivot"]["y"]
    dirs = ((-1, 0), (1, 0)) if axis == "H" else ((0, -1), (0, 1))
    result = []
    for dx, dy in dirs:
        nx, ny = x + dx, y + dy
        while _inside(nx, ny) and game["cases"][ny][nx] is None:
            result.append({"x": nx, "y": ny})
            nx, ny = nx + dx, ny + dy
    return result

def _diagonal_destinations(game):
    x, y = game["pivot"]["x"], game["pivot"]["y"]
    result = []
    for dx, dy in ((-1,-1),(1,-1),(-1,1),(1,1)):
        nx, ny = x + dx, y + dy
        while _inside(nx, ny) and game["cases"][ny][nx] is None:
            result.append({"x": nx, "y": ny})
            nx, ny = nx + dx, ny + dy
    return result

def _can_move(game, side):
    stock = game["stock"][side]
    return bool(_destinations(game, _axis(side)) or
                (stock["virage"] and _destinations(game, _axis(_other(side)))) or
                (stock["diagonale"] and _diagonal_destinations(game)))

def _finish_turn(game):
    game["coups"] += 1
    game["tour"] = _other(game["tour"])
    if game["coups"] == 1:
        game["attenteEchange"] = True
    elif not _can_move(game, game["tour"]):
        game["gagnant"] = _other(game["tour"])

def _move(game, side, target):
    x0, y0 = game["pivot"]["x"], game["pivot"]["y"]
    x1, y1 = target["x"], target["y"]
    dx = (x1 > x0) - (x1 < x0)
    dy = (y1 > y0) - (y1 < y0)
    x, y = x0, y0
    while (x, y) != (x1, y1):
        x, y = x + dx, y + dy
        game["cases"][y][x] = {"type": "trace", "cote": side}
    game["traits"].append({"x1": x0, "y1": y0, "x2": x1, "y2": y1, "cote": side})
    game["pivot"] = {"x": x1, "y": y1}

def apply_action(game, side, action, inventory=None):
    """Apply one validated action. inventory is optional DB-backed {tp,diagonale,pivot}."""
    if side not in ("R", "B") or not isinstance(action, dict): return {"ok": False, "err": "Action invalide."}
    if game["gagnant"]: return {"ok": False, "err": "Partie terminée."}
    kind = action.get("type")
    if game["attenteEchange"]:
        if side != "B" or kind != "echange" or not isinstance(action.get("garder"), bool):
            return {"ok": False, "err": "Bleu doit choisir garder ou échanger."}
        if not action["garder"]: game["noms"]["R"], game["noms"]["B"] = game["noms"]["B"], game["noms"]["R"]
        game["attenteEchange"] = False
        if not _can_move(game, "B"): game["gagnant"] = "R"
        return {"ok": True, "action": "echange"}
    if side != game["tour"]: return {"ok": False, "err": "Ce n'est pas à vous de jouer."}
    if game["enTp"] and kind != "tp_suite": return {"ok": False, "err": "Déplacement obligatoire après téléportation."}
    target = action.get("to")
    if kind == "tp_suite":
        sub = action.get("deplacement") or {}
        return apply_action(game, side, sub, inventory) if not game["enTp"] else _apply_tp_move(game, side, sub, inventory)
    if kind == "echange": return {"ok": False, "err": "Aucun échange en attente."}
    if kind == "borne":
        if not isinstance(target, dict) or not _inside(target.get("x"), target.get("y")): return {"ok": False, "err": "Cible invalide."}
        x,y=target["x"],target["y"]
        if game["stock"][side]["bornes"] < 1 or game["cases"][y][x] is not None: return {"ok": False, "err": "Borne impossible ici."}
        if not _can_move(game, side): return {"ok": False, "err": "Aucun mouvement possible : une borne ne sauve pas."}
        game["cases"][y][x]={"type":"borne","cote":side}; game["stock"][side]["bornes"]-=1; _finish_turn(game)
        return {"ok": True, "action": kind}
    if kind == "tp":
        if game["stock"][side]["tp"] < 1 or (inventory is not None and inventory.get("tp",0)<1): return {"ok": False,"err":"Téléportation indisponible."}
        if not isinstance(target,dict) or not _inside(target.get("x"),target.get("y")): return {"ok":False,"err":"Cible invalide."}
        x,y=target["x"],target["y"]
        if game["cases"][y][x] is not None or (x,y)==(game["pivot"]["x"],game["pivot"]["y"]): return {"ok":False,"err":"Point bloqué."}
        game["cases"][game["pivot"]["y"]][game["pivot"]["x"]]={"type":"trace","cote":side}
        game["cases"][y][x]={"type":"trace","cote":side}; game["pivot"]={"x":x,"y":y}
        game["stock"][side]["tp"]-=1; game["enTp"]=True
        return {"ok":True,"action":"tp","attenteDeplacement":True,"consomme":{"tp":1}}
    return _apply_regular_move(game, side, kind, target, inventory)

def _apply_tp_move(game, side, action, inventory):
    game["enTp"] = False
    result = _apply_regular_move(game, side, action.get("type"), action.get("to"), inventory)
    if not result["ok"]: game["enTp"] = True
    else: result["action"] = "tp_suite"
    return result

def _apply_regular_move(game, side, kind, target, inventory):
    if not isinstance(target,dict) or not _inside(target.get("x"),target.get("y")): return {"ok":False,"err":"Cible invalide."}
    stock=game["stock"][side]
    if kind == "glisser": valid=_destinations(game,_axis(side)); cost=None
    elif kind == "virage":
        if stock["virage"]<1 or (inventory is not None and inventory.get("pivot",0)<1): return {"ok":False,"err":"Virage indisponible."}
        valid=_destinations(game,_axis(_other(side))); cost="pivot"
    elif kind == "diagonale":
        if stock["diagonale"]<1 or (inventory is not None and inventory.get("diagonale",0)<1): return {"ok":False,"err":"Diagonale indisponible."}
        valid=_diagonal_destinations(game); cost="diagonale"
    else: return {"ok":False,"err":"Type de coup inconnu."}
    if target not in valid: return {"ok":False,"err":"Déplacement invalide."}
    _move(game,side,target)
    if kind == "virage": stock["virage"]-=1
    if kind == "diagonale": stock["diagonale"]-=1
    _finish_turn(game)
    return {"ok":True,"action":kind,"consomme":{cost:1} if cost else {}}

def public_state(game):
    return {key: deepcopy(game[key]) for key in ("cases","pivot","traits","tour","stock","noms","coups","attenteEchange","enTp","gagnant")}
