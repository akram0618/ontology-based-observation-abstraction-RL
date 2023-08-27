import pickle
from simulator.simulator import Simulator
from controller.PID.PIDController import PIDController
from controller.RL.DDPG import DDPGController
from controller.RL.PPO import PPOController
from controller.RL.SAC import SACController

def train_pid(sim_file):
    sim = Simulator.from_json(sim_file)
    pid = PIDController()
    pid.train(sim, response_step_count=10)
    with open('controller/saved/PID.pkl', 'wb') as f:
        pickle.dump(pid, f)
    print("PID saved...")

def train_rl(sim_file):
    sim = Simulator.from_json(sim_file)
    '''sac = SACController(sim)
    sac.train(sim)
    sac.save('controller/saved/SAC/')'''

    ppo = PPOController(sim)
    print("START of Train!")
    ppo.train(sim)
    print("END of Train!")
    ppo.save('controller/saved/PPO/')
    print("PPO saved...")

    ddpg = DDPGController(sim)
    ddpg.train(sim)
    ddpg.save('controller/saved/DDPG/')
    print("DDPG saved...")


if __name__== "__main__":
    #train_pid("simulator/config/simulation1.json")
    train_rl("simulator/config/simulation1.json")
