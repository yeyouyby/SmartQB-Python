import math
import random

class SimulatedAnnealingExamBuilder:
    def __init__(self, question_pool, target_score=100, target_difficulty=0.65, difficulty_weight=100.0):
        # pool is a list of dicts: {"id": 1, "score": 5, "difficulty": 0.5, "tags": ["math"]}
        self.pool = question_pool
        self.target_score = target_score
        self.target_difficulty = target_difficulty
        self.difficulty_weight = difficulty_weight

    def energy(self, state):
        # State is a subset of pool
        if not state:
            return float('inf')

        current_score = sum(q["score"] for q in state)
        current_diff = sum(q["difficulty"] for q in state) / len(state)

        # Penalty for deviation from target score and difficulty
        score_penalty = abs(current_score - self.target_score)
        diff_penalty = abs(current_diff - self.target_difficulty) * self.difficulty_weight

        return score_penalty + diff_penalty

    def get_neighbor(self, current_state):
        # Swap one question with a random one from the pool not in the state
        if not current_state:
            return random.sample(self.pool, min(10, len(self.pool)))

        neighbor = current_state.copy()

        # Remove a random item
        idx_to_remove = random.randint(0, len(neighbor) - 1)
        removed = neighbor.pop(idx_to_remove)

        in_state_ids = {q["id"] for q in neighbor}

        # Efficient random sampling instead of list comprehension for large pools
        attempts = 0
        candidate = None
        while attempts < 100:
            potential = random.choice(self.pool)
            if potential["id"] not in in_state_ids:
                candidate = potential
                break
            attempts += 1

        if candidate:
            neighbor.append(candidate)
        else:
            neighbor.append(removed) # fallback if pool is completely saturated or unlucky

        return neighbor

    def build_exam(self, initial_temp=100.0, cooling_rate=0.99, max_iterations=1000):
        if not self.pool:
            return []

        # Initial guess based on score
        avg_score = sum(float(q.get("score", 1)) for q in self.pool) / len(self.pool)
        estimated_count = max(1, int(round(self.target_score / avg_score))) if avg_score > 0 else min(20, len(self.pool))
        n_initial = min(estimated_count, len(self.pool))

        current_state = random.sample(self.pool, n_initial)
        current_energy = self.energy(current_state)

        best_state = current_state
        best_energy = current_energy

        temp = initial_temp

        for _ in range(max_iterations):
            neighbor = self.get_neighbor(current_state)
            neighbor_energy = self.energy(neighbor)

            # If neighbor is better, accept it
            if neighbor_energy < current_energy:
                current_state = neighbor
                current_energy = neighbor_energy

                if current_energy < best_energy:
                    best_state = current_state
                    best_energy = current_energy
            else:
                # Accept worse state with probability based on temp
                prob = math.exp((current_energy - neighbor_energy) / temp)
                if random.random() < prob:
                    current_state = neighbor
                    current_energy = neighbor_energy

            temp *= cooling_rate

            if temp < 0.01:
                break

        return best_state
