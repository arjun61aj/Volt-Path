"""Generic A* route search. Ranking is deliberately kept in recommendation.py."""
import heapq
from services.distance import haversine_km, road_distance_km

def build_station_graph(user, stations, neighbours=4):
    coords={"user":user, **{f"s{x['station_id']}":(x['latitude'],x['longitude']) for x in stations}}
    graph={n:{} for n in coords}
    names=list(coords)
    for node in names:
        nearest=sorted((haversine_km(*coords[node],*coords[o]),o) for o in names if o!=node)[:neighbours]
        for _,other in nearest:
            cost=road_distance_km(*coords[node],*coords[other])
            graph[node][other]=cost; graph[other][node]=cost
    return graph,coords

def astar(graph, coords, start, goal):
    frontier=[(0,start)]; came={start:None}; cost={start:0.0}
    while frontier:
        _,node=heapq.heappop(frontier)
        if node==goal: break
        for nxt,edge in graph[node].items():
            new=cost[node]+edge
            if nxt not in cost or new<cost[nxt]:
                cost[nxt]=new; came[nxt]=node
                heuristic=haversine_km(*coords[nxt],*coords[goal])
                heapq.heappush(frontier,(new+heuristic,nxt))
    if goal not in came: return [],float("inf")
    path=[]; n=goal
    while n is not None: path.append(n); n=came[n]
    return path[::-1],cost[goal]
