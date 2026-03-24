import math
import random

class SimulatedAnnealingExamBuilder:
    def __init__(self, question_pool, target_score=100, target_difficulty=0.65):
        # pool is a list of dicts: {"id": 1, "score": 5, "difficulty": 0.5, "tags": ["math"]}
        self.pool = question_pool
        self.target_score = target_score
        self.target_difficulty = target_difficulty

    def energy(self, state):
        # State is a subset of pool
        current_score = sum(q["score"] for q in state)
        if not state:
            return float('inf')

        current_diff = sum(q["difficulty"] for q in state) / len(state)

        # Penalty for deviation from target score and difficulty
        score_penalty = abs(current_score - self.target_score)
        diff_penalty = abs(current_diff - self.target_difficulty) * 100 # weight it

        return score_penalty + diff_penalty

    def get_neighbor(self, current_state):
        # Swap one question with a random one from the pool not in the state
        if not current_state:
            return random.sample(self.pool, min(10, len(self.pool)))

        neighbor = current_state.copy()

        # Remove a random item
        idx_to_remove = random.randint(0, len(neighbor) - 1)
        removed = neighbor.pop(idx_to_remove)

        # Add a random item not in neighbor
        in_state_ids = {q["id"] for q in neighbor}
        candidates = [q for q in self.pool if q["id"] not in in_state_ids]

        if candidates:
            neighbor.append(random.choice(candidates))
        else:
            neighbor.append(removed) # fallback

        return neighbor

    def build_exam(self, initial_temp=100.0, cooling_rate=0.99, max_iterations=1000):
        # Initial guess (e.g., random 20 questions)
        n_initial = min(20, len(self.pool))
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
