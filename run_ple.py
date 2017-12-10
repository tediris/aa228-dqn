from ple.games.flappybird import FlappyBird
from ple import PLE
import random
# from dqn import preprocess_observation

class RandomAgent:
    def __init__(self, actions):
        self.actions = actions
        print(actions)

    def pickAction(self, reward, observation):
        if random.uniform(0, 1) > 0.7:
            return 0
        else:
            return 1

game = FlappyBird()

p = PLE(game, fps=30, display_screen=True)
agent = RandomAgent(actions=p.getActionSet())

p.init()
reward = 0.0

nb_frames = 10000
for i in range(nb_frames):
   if p.game_over():
           p.reset_game()

   observation = p.getScreenRGB()
   # processed = preprocess_observation(observation)
   action = agent.pickAction(reward, observation)
   action = None
   reward = p.act(action)
