import os
import pickle
from simulator.statistics import Statistics
from simulator.simulator import Simulator
from controller.RL.DDPG import DDPGController
from controller.RL.PPO import PPOController
from controller.RL.SAC import SACController

def eval(sim_path, models_path):
    sim=Simulator.from_json(sim_path)
    controllers=[]
    model_files = [f for f in os.listdir(models_path) if os.path.isfile(os.path.join(models_path, f))]
    for file_name in model_files:
        model_name = file_name.split('.')[0]
        with open(os.path.join(models_path, file_name), 'rb') as f:
            model = pickle.load(f)
            controllers.append((model_name,model))
    ddpg = DDPGController(sim)
    ddpg.load('controller/saved/DDPG_pretrain/')
    controllers.append(('DDPG',ddpg))

    ppo = PPOController(sim)
    ppo.load('controller/saved/PPO_pretrain/')
    #ppo.load('controller/saved/PPO/')
    controllers.append(('PPO',ppo))

    stat = Statistics(sim, controllers)
    stat.print_result()
    stat.plot()



if __name__== "__main__":
    eval("simulator/config/simulation1.json", "controller/saved")
