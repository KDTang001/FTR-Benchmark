'''

'''
import sys, os

import gym

sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
from utils.path import apply_project_directory
apply_project_directory()

from utils.path import project_dir_join

from omniisaacgymenvs.utils.hydra_cfg.hydra_utils import *
from omniisaacgymenvs.utils.hydra_cfg.reformat import omegaconf_to_dict, print_dict
from omniisaacgymenvs.utils.rlgames.rlgames_utils import RLGPUEnv
from omniisaacgymenvs.utils.config_utils.path_utils import retrieve_checkpoint_path
from omniisaacgymenvs.envs.vec_env_rlgames import VecEnvRLGames

import datetime
import hydra
from omegaconf import DictConfig

from rl_games.common import env_configurations, vecenv


def process_sarl(env, cfg_dict):
    cfg_train = cfg_dict['train']['params']

    learn_cfg = cfg_train["learn"]
    is_testing = learn_cfg["test"]

    # is_testing = True
    # Override resume and testing flags if they are passed as parameters.
    if cfg_dict['checkpoint'] != "":
        is_testing = True
        chkpt_path = cfg_dict['checkpoint']

    if cfg_dict['max_iterations'] != -1:
        cfg_train["learn"]["max_iterations"] = cfg_dict['checkpoint']

    logdir = cfg_train["learn"]['full_experiment_name']

    from algorithms.rl.ppo import PPO
    from algorithms.rl.sac import SAC
    from algorithms.rl.td3 import TD3
    from algorithms.rl.ddpg import DDPG
    from algorithms.rl.trpo import TRPO

    class Wrap(gym.Wrapper):

        def reset(self):
            return self.env.reset()['obs']

        def step(self, action):
            obs, rew, done, info = self.env.step(action)
            return obs['obs'], rew, done, info
        def get_state(self):
            return self.env._task.obs_buf

    """Set up the algo system for training or inferencing."""
    model = eval(cfg_train['algo']['name'].upper())(vec_env=Wrap(env),
              cfg_train = cfg_train,
              device=cfg_train['learn']['device'],
              sampler=learn_cfg.get("sampler", 'sequential'),
              log_dir=logdir,
              is_testing=is_testing,
              print_log=learn_cfg["print_log"],
              apply_reset=False,
              asymmetric=(env.num_states > 0)
              )

    # ppo.test("/home/hp-3070/logs/demo/scissors/ppo_seed0/model_6000.pt")
    if is_testing and cfg_dict['checkpoint'] != "":
        print("Loading model from {}".format(chkpt_path))
        model.test(chkpt_path)
    elif cfg_dict['checkpoint'] != "":
        print("Loading model from {}".format(chkpt_path))
        model.load(chkpt_path)

    return model

@hydra.main(config_name="config", config_path=project_dir_join('cfg'))
def parse_hydra_configs(cfg: DictConfig):

    time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    headless = cfg.headless
    rank = int(os.getenv("LOCAL_RANK", "0"))
    if cfg.multi_gpu:
        cfg.device_id = rank
        cfg.rl_device = f'cuda:{rank}'

    enable_viewport = "enable_cameras" in cfg.task.sim and cfg.task.sim.enable_cameras
    env = VecEnvRLGames(headless=headless, sim_device=cfg.device_id, enable_livestream=cfg.enable_livestream, enable_viewport=enable_viewport)

    if cfg.checkpoint:
        cfg.checkpoint = retrieve_checkpoint_path(cfg.checkpoint)
        if cfg.checkpoint is None:
            quit()

    cfg_dict = omegaconf_to_dict(cfg)
    print_dict(cfg_dict)

    from omni.isaac.core.utils.torch.maths import set_seed
    cfg.seed = set_seed(cfg.seed, torch_deterministic=cfg.torch_deterministic)
    cfg_dict['seed'] = cfg.seed

    from pumbaa import initialize_task

    task = initialize_task(cfg_dict, env)

    if cfg_dict['train']['params']['algo']['name'] in ["ppo", "ddpg", "sac", "td3", "trpo"]:

        sarl = process_sarl(env, cfg_dict)

        iterations = cfg_dict["max_iterations"]

        sarl.run(num_learning_iterations=int(iterations), log_interval=cfg_dict['train']['params']["learn"]["save_interval"])

    else:
        raise NotImplementedError()

    env.close()

if __name__ == '__main__':
    parse_hydra_configs()