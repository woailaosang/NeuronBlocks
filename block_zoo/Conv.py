# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT license.

import torch
import torch.nn as nn
import torch.nn.functional as F
from collections import OrderedDict

from block_zoo.BaseLayer import BaseLayer, BaseConf
from utils.DocInherit import DocInherit


class ConvConf(BaseConf):
    """ Configuration of Conv

    Args:
        stride (int): the stride of the convolving kernel. Can be a single number or a tuple (sH, sW). Default: 1
        padding (int): implicit zero paddings on both sides of the input. Can be a single number or a tuple (padH, padW). Default: 0
        window_size (int): actually, the window size is (window_size, feature_dim), because for NLP tasks, 1d convolution is more commonly used.
        input_channel_num (int): for NLP tasks, input_channel_num would always be 1
        output_channel_num (int): number of feature maps
        batch_norm (bool): If True, apply batch normalization before activation
        activation (string): activation functions, e.g. ReLU

    """
    def __int__(self, **kwargs):
        super(ConvConf, self).__init__(**kwargs)

    @DocInherit
    def default(self):
        self.stride = 1
        self.padding = 0
        self.window_size = 3
        self.input_channel_num = 1      # for NLP tasks, input_channel_num would always be 1
        self.output_channel_num = 16
        self.batch_norm = True
        self.activation = 'ReLU'

    @DocInherit
    def declare(self):
        self.num_of_inputs = 1
        self.input_ranks = [3]

    @DocInherit
    def inference(self):
        self.output_dim = [-1]
        if self.input_dims[0][1] != -1:
            self.output_dim.append((self.input_dims[0][1] - self.window_size) // self.stride + 1)
        else:
            self.output_dim.append(-1)
        self.output_dim.append(self.output_channel_num)

        super(ConvConf, self).inference()  # PUT THIS LINE AT THE END OF inference()

    @DocInherit
    def verify_before_inference(self):
        super(ConvConf, self).verify_before_inference()
        necessary_attrs_for_user = ['output_channel_num']
        for attr in necessary_attrs_for_user:
            self.add_attr_exist_assertion_for_user(attr)

    @DocInherit
    def verify(self):
        super(ConvConf, self).verify()

        necessary_attrs_for_user = ['stride', 'padding', 'window_size', 'input_channel_num', 'output_channel_num', 'activation']
        for attr in necessary_attrs_for_user:
            self.add_attr_exist_assertion_for_user(attr)


class Conv(BaseLayer):
    """ Convolution along just 1 direction

    Args:
        layer_conf (ConvConf): configuration of a layer
    """
    def __init__(self, layer_conf):
        super(Conv, self).__init__(layer_conf)
        self.layer_conf = layer_conf
        if layer_conf.activation:
            self.activation = eval("nn." + self.layer_conf.activation)()
        else:
            self.activation = None

        self.filters = nn.ParameterList([nn.Parameter(torch.randn(layer_conf.output_channel_num,
            layer_conf.input_channel_num, layer_conf.window_size, layer_conf.input_dims[0][-1],
            requires_grad=True).float())])

        if layer_conf.batch_norm:
            self.batch_norm = nn.BatchNorm2d(layer_conf.output_channel_num)    # the output_chanel of Conv is the input_channel of BN
        else:
            self.batch_norm = None

    def forward(self, string, string_len=None):
        """ process inputs

        Args:
            string (Tensor): tensor with shape: [batch_size, seq_len, feature_dim]
            string_len (Tensor):  [batch_size]

        Returns:
            Tensor: shape: [batch_size, (seq_len - conv_window_size) // stride + 1, output_channel_num]

        """
        if string_len is not None:
            string_len_val = string_len.cpu().data.numpy()
            masks = []
            for i in range(len(string_len)):
                masks.append(torch.cat([torch.ones(string_len_val[i]), torch.zeros(string.shape[1] - string_len_val[i])]))
            masks = torch.stack(masks).view(string.shape[0], string.shape[1], 1).expand_as(string)
            if self.is_cuda():
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                masks = masks.to(device)
            string = string * masks

        string = torch.unsqueeze(string, 1)     # [batch_size, input_channel_num=1, seq_len, feature_dim]
        string_out = F.conv2d(string, self.filters[0], stride=self.layer_conf.stride, padding=self.layer_conf.padding)
        if hasattr(self, 'batch_norms') and self.batch_norm:
            string_out = self.batch_norm(string_out)

        string_out = torch.squeeze(string_out, 3).permute(0, 2, 1)

        if self.activation:
            string_out = self.activation(string_out)
        if string_len is not None:
            string_len_out = (string_len - self.layer_conf.window_size) // self.layer_conf.stride + 1
        else:
            string_len_out = None
        return string_out, string_len_out
