import torch
from thop import profile


def FLOPs_and_Params(model, img_size, len_clip, device, stream=False):
    # generate init video clip
    video_clip = [torch.randn(1, 3, img_size, img_size).to(device) for _ in range(len_clip)]

    if stream:
        # set eval mode
        model.trainable = False
        model.stream_infernce = True
        model.initialization = True
        model.eval()
        
        # init inference
        _, _, _ = model(video_clip)

        # generate a cur frame
        cur_frame = torch.randn(1, 3, img_size, img_size).to(device)

        print('==============================')
        flops, params = profile(model, inputs=(cur_frame, ))
        print('==============================')
        print('FLOPs : {:.2f} B'.format(flops / 1e9))
        print('Params : {:.2f} M'.format(params / 1e6))

        # set train mode.
        model.trainable = True
        model.stream_infernce = False
        model.initialization = False
        model.train()

    else:
        # set eval mode
        model.trainable = False
        model.eval()

        print('==============================')
        flops, params = profile(model, inputs=(video_clip, ))
        print('==============================')
        print('FLOPs : {:.2f} B'.format(flops / 1e9))
        print('Params : {:.2f} M'.format(params / 1e6))
        # set train mode.
        model.trainable = True
        model.train()


if __name__ == "__main__":
    pass
